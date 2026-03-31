"""
Servo Controller — Gesture API for the robot's arms.

Backends:
  1. ESP32 Bridge (preferred) — sends commands via serial to ESP32
  2. RPi GPIO (legacy) — direct PWM on Pi GPIO pins
  3. Stub mode — prints to terminal for laptop testing

The same gesture API works regardless of backend.
"""

import time
import threading

# Try to import ESP32 bridge
try:
    from esp32_bridge import ESP32Bridge
    _BRIDGE_AVAILABLE = True
except ImportError:
    _BRIDGE_AVAILABLE = False

# Try RPi.GPIO as legacy fallback
try:
    import RPi.GPIO as GPIO
    _GPIO_AVAILABLE = True
except ImportError:
    _GPIO_AVAILABLE = False


class ServoController:
    def __init__(self, esp32_bridge=None):
        """
        Args:
            esp32_bridge: Optional ESP32Bridge instance. If provided, servos
                          are controlled via ESP32. If None, falls back to
                          GPIO or stub mode.
        """
        # Angle definitions (same for all backends)
        self.HOME_ANGLES = {
            'L_WRIST': 70.0, 'L_ELBOW': 160.0,
            'R_WRIST': 40.0, 'R_ELBOW': 90.0
        }
        self.MIN_ANGLES = {
            'L_WRIST': 70.0, 'L_ELBOW': 160.0,
            'R_WRIST': 40.0, 'R_ELBOW': 90.0
        }
        self.MAX_ANGLES = {
            'L_WRIST': 20.0, 'L_ELBOW': 110.0,
            'R_WRIST': 70.0, 'R_ELBOW': 145.0
        }
        self.current_angles = {j: self.HOME_ANGLES[j] for j in self.HOME_ANGLES}
        self.target_angles = {j: self.HOME_ANGLES[j] for j in self.HOME_ANGLES}
        self.running = True
        self.pins = {
            'L_WRIST': None, 'L_ELBOW': None,
            'R_WRIST': None, 'R_ELBOW': None
        }

        # ── Determine backend ───────────────────────────────────
        self.bridge = esp32_bridge  # ESP32Bridge instance or None
        self.backend = 'stub'
        self.connected = False
        self._dirty = False  # Tracks if angles changed since last ESP32 send

        if self.bridge and self.bridge.connected:
            self.backend = 'esp32'
            self.connected = True
            print("[Servo] Backend: ESP32 (serial)")
            # Start batch sender for ESP32
            self._sender_thread = threading.Thread(target=self._esp32_send_loop, daemon=True)
            self._sender_thread.start()
        elif _GPIO_AVAILABLE:
            self.backend = 'gpio'
            self._init_gpio()
        else:
            print("[Servo] Backend: STUB (terminal only)")

    # ── GPIO Legacy Init ──────────────────────────────────────
    def _init_gpio(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        self.pins = {
            'L_WRIST': 17, 'L_ELBOW': 18,
            'R_WRIST': 27, 'R_ELBOW': 22
        }
        self.pwms = {}
        self.frequency = 50
        self.min_dc = 2.5
        self.max_dc = 12.5
        try:
            for joint, pin in self.pins.items():
                GPIO.setup(pin, GPIO.OUT)
                pwm = GPIO.PWM(pin, self.frequency)
                pwm.start(0)
                self.pwms[joint] = pwm
            self.connected = True
            self.backend = 'gpio'
            print("[Servo] Backend: RPi GPIO")
            for joint in self.pins:
                self._apply_angle_gpio(joint, self.HOME_ANGLES[joint])
        except Exception as e:
            print(f"[Servo] GPIO Setup Error: {e}")
            self.connected = False
            self.backend = 'stub'

        if self.connected and self.backend == 'gpio':
            self.move_to_neutral()
            self.smoothing_thread = threading.Thread(target=self._smooth_move_loop, daemon=True)
            self.smoothing_thread.start()

    # ── ESP32 Batch Sender ─────────────────────────────────────
    def _esp32_send_loop(self):
        """Sends angle updates to ESP32 at ~25Hz, only when changed."""
        while self.running:
            if self._dirty and self.bridge and self.bridge.connected:
                self._dirty = False
                self.bridge.set_arm_angles(
                    l_elbow=int(self.current_angles['L_ELBOW']),
                    l_wrist=int(self.current_angles['L_WRIST']),
                    r_elbow=int(self.current_angles['R_ELBOW']),
                    r_wrist=int(self.current_angles['R_WRIST'])
                )
            time.sleep(0.04)  # 25Hz

    # ── GPIO Smooth Move Loop ─────────────────────────────────
    def _smooth_move_loop(self):
        while self.running:
            if self.connected and self.backend == 'gpio':
                moved = False
                for joint in self.pins:
                    diff = self.target_angles[joint] - self.current_angles[joint]
                    if abs(diff) > 0.5:
                        step = max(-5.0, min(5.0, diff * 0.2))
                        self.current_angles[joint] += step
                        self._apply_angle_gpio(joint, self.current_angles[joint])
                        moved = True
                time.sleep(0.02 if moved else 0.05)
            else:
                time.sleep(0.1)

    def _apply_angle_gpio(self, joint, angle):
        dc = self.min_dc + (angle / 180.0) * (self.max_dc - self.min_dc)
        self.pwms[joint].ChangeDutyCycle(dc)

    # ═════════════════════════════════════════════════════════════
    #  PUBLIC API (same for all backends)
    # ═════════════════════════════════════════════════════════════

    def set_angle(self, joint, angle):
        """Sets target angle for a joint, constrained by defined limits."""
        if joint not in self.pins:
            return
        lower = min(self.MIN_ANGLES[joint], self.MAX_ANGLES[joint])
        upper = max(self.MIN_ANGLES[joint], self.MAX_ANGLES[joint])
        clamped = max(lower, min(upper, angle))
        self.target_angles[joint] = clamped
        self.current_angles[joint] = clamped

        if self.backend == 'esp32':
            self._dirty = True
        elif self.backend == 'stub':
            print(f"  [Servo] {joint}: {clamped:.0f}°")

    def move_to_neutral(self):
        """Sets all joints to home angles."""
        if self.backend == 'stub':
            print("  [Servo] All joints → HOME")
        if self.backend == 'esp32' and self.bridge:
            self.bridge.arms_home()
            for j in self.pins:
                self.current_angles[j] = self.HOME_ANGLES[j]
                self.target_angles[j] = self.HOME_ANGLES[j]
        else:
            for joint in self.pins:
                self.set_angle(joint, self.HOME_ANGLES[joint])

    # ── Gestures ─────────────────────────────────────────────────

    def gesture_wave(self):
        """Performs a waving gesture."""
        def wave():
            if self.backend == 'stub':
                print("🤚 [Gesture] Wave started")
            self.set_angle('R_WRIST', 150)
            time.sleep(0.5)
            for _ in range(3):
                self.set_angle('R_ELBOW', 60)
                time.sleep(0.4)
                self.set_angle('R_ELBOW', 120)
                time.sleep(0.4)
            self.move_to_neutral()
            if self.backend == 'stub':
                print("🤚 [Gesture] Wave finished")
        threading.Thread(target=wave, daemon=True).start()

    def gesture_talking(self, duration=2.0):
        """Random arm movements to simulate talking."""
        import random
        def talk():
            if self.backend == 'stub':
                print("🗣️  [Gesture] Talking started")
            end_time = time.time() + duration
            while time.time() < end_time:
                joint = random.choice(list(self.pins.keys()))
                base = self.HOME_ANGLES[joint]
                angle = base + random.randint(0, 50)
                self.set_angle(joint, angle)
                time.sleep(random.uniform(0.3, 0.6))
            self.move_to_neutral()
            if self.backend == 'stub':
                print("🗣️  [Gesture] Talking finished")
        threading.Thread(target=talk, daemon=True).start()

    def gesture_thinking(self, stop_event):
        """Alternating arm motion: one arm UP+wrist RIGHT, other DOWN+wrist LEFT."""
        if self.backend == 'stub':
            print("🤔 [Gesture] Thinking started — alternating arms...")
        cycle = 0
        while not stop_event.is_set():
            cycle += 1
            if self.backend == 'stub':
                print(f"  [Think cycle {cycle}] Left UP+R, Right DOWN+L")
            self.set_angle('L_ELBOW', self.MAX_ANGLES['L_ELBOW'])
            self.set_angle('L_WRIST', self.MAX_ANGLES['L_WRIST'])
            self.set_angle('R_ELBOW', self.HOME_ANGLES['R_ELBOW'])
            self.set_angle('R_WRIST', self.HOME_ANGLES['R_WRIST'])
            if stop_event.wait(0.8):
                break

            if self.backend == 'stub':
                print(f"  [Think cycle {cycle}] Left DOWN+L, Right UP+R")
            self.set_angle('L_ELBOW', self.HOME_ANGLES['L_ELBOW'])
            self.set_angle('L_WRIST', self.HOME_ANGLES['L_WRIST'])
            self.set_angle('R_ELBOW', self.MAX_ANGLES['R_ELBOW'])
            self.set_angle('R_WRIST', self.MAX_ANGLES['R_WRIST'])
            if stop_event.wait(0.8):
                break

        self.move_to_neutral()
        if self.backend == 'stub':
            print("🤔 [Gesture] Thinking finished — arms back to home")

    # ── Cleanup ──────────────────────────────────────────────────

    def cleanup(self):
        self.running = False
        if hasattr(self, 'smoothing_thread'):
            self.smoothing_thread.join(timeout=1.0)
        if self.backend == 'gpio' and self.connected:
            for pwm in self.pwms.values():
                pwm.stop()
            GPIO.cleanup()


# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    # If port is provided, use ESP32 backend
    if len(sys.argv) > 1:
        port = sys.argv[1]
        print(f"Testing with ESP32 on {port}...")
        bridge = ESP32Bridge(port=port)
        sc = ServoController(esp32_bridge=bridge)
    else:
        print("No port given — testing in stub mode")
        print("Usage: python3 servos.py /dev/ttyUSB0")
        sc = ServoController()

    try:
        print("\n1. Wave gesture...")
        sc.gesture_wave()
        time.sleep(3)

        print("\n2. Talking gesture (3s)...")
        sc.gesture_talking(duration=3)
        time.sleep(4)

        print("\n3. Thinking gesture (4s)...")
        stop = threading.Event()
        t = threading.Thread(target=sc.gesture_thinking, args=(stop,))
        t.start()
        time.sleep(4)
        stop.set()
        t.join()

        print("\nAll tests done! ✅")
    finally:
        sc.cleanup()
