import cv2
import mediapipe as mp
import time
import threading
import numpy as np

class VisionHandler:
    def __init__(self):
        # ── MediaPipe Face Detection (Bypassing broken OpenCV CascadeClassifier) ──
        self.mp_face_detection = mp.solutions.face_detection
        self.face_detection = self.mp_face_detection.FaceDetection(
            model_selection=0, # 0 = fast/short-range (<2m), perfect for reception bot
            min_detection_confidence=0.6
        )

        # ── MediaPipe Pose for wave detection (already optimal — MoveNet internally) ──
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
            model_complexity=0   # Fastest pose model
        )

        self.cap = None
        self.is_running = False

        # Detection state (written by vision thread, read by main thread)
        self.human_detected = False
        self.wave_detected = False
        self.person_nearby = False
        self.active_speaker_offset = 0.0  # -1.0 (left) to 1.0 (right) from largest face
        self.current_frame = None

        self.lock = threading.Lock()
        self.last_wave_time = 0
        self._frame_counter = 0

        # Camera / processing sizes (tuned for Pi 4 performance)
        self.CAP_WIDTH   = 480
        self.CAP_HEIGHT  = 360
        self.PROC_WIDTH  = 240
        self.PROC_HEIGHT = 180

        # Proximity thresholds (face height / frame height at processing resolution)
        # Enter "nearby" when face is large enough (~1m away): 8%
        # Exit only when face is very small (~2m+ away): 4%
        # Wide gap prevents flickering at boundary
        self.PROXIMITY_ENTER = 0.08
        self.PROXIMITY_EXIT  = 0.04

        # Require many consecutive "no face" frames before marking human as gone
        self._no_face_counter = 0
        self._NO_FACE_THRESHOLD = 15  # ~0.75 seconds at 20fps

    # ── Camera setup ──────────────────────────────────────────────────────────

    def find_camera(self):
        for i in range(3):
            tmp = cv2.VideoCapture(i)
            if tmp.isOpened():
                tmp.release()
                return i
        return 0

    def start(self):
        cam_idx = self.find_camera()
        self.cap = cv2.VideoCapture(cam_idx, cv2.CAP_V4L2)  # V4L2 avoids GStreamer overhead on Pi
        if not self.cap.isOpened():
            return False
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.CAP_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.CAP_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, 15)
        self.is_running = True
        self.thread = threading.Thread(target=self._process_loop, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        self.is_running = False
        if self.cap:
            self.cap.release()

    def reset_wave(self):
        """Reset wave state before entering the wave-wait phase."""
        with self.lock:
            self.wave_detected = False
            self.last_wave_time = 0

    # ── Main processing loop ──────────────────────────────────────────────────

    def _process_loop(self):
        while self.is_running:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.03)
                continue

            frame = cv2.flip(frame, 1)

            # Store full-res frame for the video stream
            with self.lock:
                self.current_frame = frame

            # Downscale to PROC resolution for all model inference
            small = cv2.resize(frame, (self.PROC_WIDTH, self.PROC_HEIGHT),
                               interpolation=cv2.INTER_LINEAR)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

            # ── Face detection via MediaPipe (every 2nd frame to save CPU) ──
            if self._frame_counter % 2 == 0:
                rgb_small = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                rgb_small.flags.writeable = False
                
                results = self.face_detection.process(rgb_small)
                
                faces = []
                if results.detections:
                    for detection in results.detections:
                        bbox = detection.location_data.relative_bounding_box
                        x = int(bbox.xmin * self.PROC_WIDTH)
                        y = int(bbox.ymin * self.PROC_HEIGHT)
                        fw = int(bbox.width * self.PROC_WIDTH)
                        fh = int(bbox.height * self.PROC_HEIGHT)
                        faces.append((x, y, fw, fh))
                        
                self._last_faces = faces
            faces = getattr(self, '_last_faces', ())

            with self.lock:
                if len(faces) > 0:
                    self.human_detected = True
                    self._no_face_counter = 0  # Reset counter on any face detection

                    # Find the largest face (closest person)
                    largest = max(faces, key=lambda f: f[2] * f[3])
                    x, y, w, h = largest

                    # Proximity: face height vs frame height
                    ratio = h / self.PROC_HEIGHT
                    if not self.person_nearby and ratio >= self.PROXIMITY_ENTER:
                        self.person_nearby = True
                    elif self.person_nearby and ratio < self.PROXIMITY_EXIT:
                        self.person_nearby = False

                    # Speaker offset: center x of largest face, normalized to [-1, 1]
                    face_center_x = x + w / 2
                    self.active_speaker_offset = ((face_center_x / self.PROC_WIDTH) - 0.5) * 2
                else:
                    # Only mark human as gone after many consecutive no-face frames
                    self._no_face_counter += 1
                    if self._no_face_counter >= self._NO_FACE_THRESHOLD:
                        self.human_detected = False
                        self.person_nearby = False
                        self.active_speaker_offset = 0.0

            # ── Pose / wave detection every 5th frame (saves ~70% pose CPU) ──
            self._frame_counter += 1
            if self._frame_counter % 5 == 0:
                rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                pose_results = self.pose.process(rgb)
                with self.lock:
                    if pose_results.pose_landmarks:
                        self._check_wave(pose_results.pose_landmarks.landmark)
                    else:
                        if time.time() - self.last_wave_time > 2.0:
                            self.wave_detected = False

            time.sleep(0.05)  # ~20fps processing cap (plenty for reception bot)

    # ── Wave detection ────────────────────────────────────────────────────────

    def _check_wave(self, landmarks):
        L = self.mp_pose.PoseLandmark
        pairs = [
            (landmarks[L.RIGHT_WRIST], landmarks[L.RIGHT_SHOULDER]),
            (landmarks[L.LEFT_WRIST],  landmarks[L.LEFT_SHOULDER]),
        ]
        is_waving = any(
            wrist.visibility > 0.5 and wrist.y < shoulder.y
            for wrist, shoulder in pairs
        )
        if is_waving:
            self.wave_detected = True
            self.last_wave_time = time.time()

    # ── Public API ────────────────────────────────────────────────────────────

    def get_status(self):
        """Returns (human_detected, wave_detected, speaker_offset, person_nearby)"""
        with self.lock:
            return (self.human_detected, self.wave_detected,
                    self.active_speaker_offset, self.person_nearby)

    def get_frame(self):
        with self.lock:
            return self.current_frame  # Callers read-only; no copy needed for streaming


if __name__ == "__main__":
    vh = VisionHandler()
    if vh.start():
        try:
            while True:
                h, w, o, n = vh.get_status()
                print(f"Human: {h}  Wave: {w}  Offset: {o:+.2f}  Nearby: {n}")
                time.sleep(0.5)
        except KeyboardInterrupt:
            vh.stop()
