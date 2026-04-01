import signal
import sys
import time
import threading
import json
import cv2
import subprocess
import webbrowser
from flask import Flask, Response, send_from_directory, request, jsonify, stream_with_context
from flask_cors import CORS
from servos import ServoController
from voice import VoiceInterface
from gemini_brain import ChatBrain
from vision import VisionHandler
from esp32_bridge import ESP32Bridge
import queue
import speech_recognition as sr

# --- Course Details ---
COURSE_DETAILS = {
    "Data Science & AI/ML": {
        "title": "Data Science & AI/ML",
        "duration": "6 Months",
        "description": (
            "Master Data Science, Artificial Intelligence, and Machine Learning from scratch. "
            "This comprehensive program covers Python programming, statistics, data visualization with Matplotlib and Seaborn, "
            "machine learning algorithms, deep learning with TensorFlow and PyTorch, natural language processing, and computer vision. "
            "You'll work on real-world projects including recommendation systems, image classification, and predictive analytics. "
            "Our graduates are placed in top companies as Data Scientists, ML Engineers, and AI Developers."
        ),
        "highlights": ["Python & Statistics", "Machine Learning & Deep Learning", "NLP & Computer Vision", "Real-world Projects", "100% Placement Support"]
    },
    "Python Full Stack": {
        "title": "Python Full Stack Development",
        "duration": "6 Months",
        "description": (
            "Become a complete Python Full Stack Developer. Learn front-end development with HTML, CSS, JavaScript, and Angular, "
            "combined with powerful back-end development using Python Django framework. "
            "This course covers database management with PostgreSQL and MySQL, RESTful API development, authentication, "
            "deployment on cloud platforms, and version control with Git. "
            "Build portfolio-worthy projects and get placement-ready with resume building and mock interviews."
        ),
        "highlights": ["HTML, CSS & JavaScript", "Angular Framework", "Python Django", "Database & API Design", "Cloud Deployment"]
    },
    "MEAN / MERN Stack": {
        "title": "MEAN / MERN Stack Development",
        "duration": "6 Months",
        "description": (
            "Learn full-stack JavaScript development with both MEAN and MERN stacks. "
            "Master MongoDB for database, Express.js for back-end, Angular and React for front-end, and Node.js for server-side development. "
            "This course covers modern JavaScript, TypeScript, state management with Redux, RESTful APIs, GraphQL, "
            "real-time applications with WebSockets, and containerization with Docker. "
            "Graduate as a versatile full-stack developer ready for the industry."
        ),
        "highlights": ["MongoDB & Express.js", "React & Angular", "Node.js", "GraphQL & WebSockets", "Docker Deployment"]
    },
    "Software Testing": {
        "title": "Software Testing & QA",
        "duration": "4 Months",
        "description": (
            "Become a certified Software Testing professional. This course covers both manual and automated testing methodologies. "
            "Learn Selenium WebDriver, TestNG, JUnit, API testing with Postman, performance testing with JMeter, "
            "and mobile testing frameworks. Master test planning, test case design, bug tracking with JIRA, "
            "and continuous integration testing. "
            "Our testing graduates are in high demand across IT companies in Kochi and Bangalore."
        ),
        "highlights": ["Manual & Automation Testing", "Selenium & TestNG", "API & Performance Testing", "JIRA & CI/CD", "Industry Certification"]
    },
    "Flutter Development": {
        "title": "Flutter Mobile App Development",
        "duration": "4 Months",
        "description": (
            "Build beautiful cross-platform mobile applications with Flutter and Dart. "
            "Learn to create stunning iOS and Android apps from a single codebase. "
            "This course covers Dart programming, Flutter widgets, state management with Provider and Bloc, "
            "Firebase integration, REST API consumption, local storage, push notifications, "
            "and publishing apps to the App Store and Google Play. "
            "Create a portfolio of mobile apps to showcase to employers."
        ),
        "highlights": ["Dart & Flutter", "iOS & Android", "Firebase Integration", "State Management", "App Store Publishing"]
    },
    "Digital Marketing": {
        "title": "Digital Marketing",
        "duration": "3 Months",
        "description": (
            "Master the art and science of Digital Marketing. Learn SEO, SEM, Google Ads, "
            "social media marketing across Facebook, Instagram, LinkedIn, and YouTube. "
            "This course covers content marketing, email marketing, Google Analytics, "
            "marketing automation, and conversion rate optimization. "
            "Get certified by Google and HubSpot, and learn to build and execute marketing strategies "
            "that drive real business results."
        ),
        "highlights": ["SEO & SEM", "Google Ads & Analytics", "Social Media Marketing", "Content Strategy", "Google & HubSpot Certifications"]
    },
    "Robotics with AI & IoT": {
        "title": "Robotics with AI & IoT",
        "duration": "6 Months",
        "description": (
            "Dive into the exciting world of Robotics, Artificial Intelligence, and Internet of Things. "
            "Learn embedded programming with Arduino and Raspberry Pi, sensor integration, motor control, "
            "computer vision with OpenCV, ROS2 for robot operating systems, and IoT protocols like MQTT. "
            "Build real robots including autonomous vehicles, robotic arms, and smart IoT devices. "
            "This hands-on course prepares you for careers in automation, robotics engineering, and IoT development."
        ),
        "highlights": ["Arduino & Raspberry Pi", "ROS2 & OpenCV", "Sensor & Motor Control", "IoT Protocols", "Build Real Robots"]
    }
}

# --- Web Server Setup ---
app = Flask(__name__, static_folder='ui')
CORS(app)
# Per-client SSE subscriber queues — each connected browser gets its own queue
_subscribers = []
_subscribers_lock = threading.Lock()
# Track the last broadcasted status so late-joining browsers can sync up immediately
_last_status = {'state': 'Idle'}

# Global reference for voice interface (set in main())
vi = None
vh = None

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(app.static_folder, path)

@app.route('/events')
def events():
    client_q = queue.Queue(maxsize=50)
    
    with _subscribers_lock:
        _subscribers.append(client_q)
        # Immediately push the last known state to this new client so the UI 
        # doesn't get stuck if it loads after the backend has already started
        client_q.put({'type': 'status', 'data': _last_status})

    def stream():
        # Yield padding bits to force Werkzeug to flush the initial headers immediately
        yield ": " + (" " * 2048) + "\n\n"
        try:
            while True:
                try:
                    event = client_q.get(timeout=30)
                    yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
                except queue.Empty:
                    # Send a keep-alive comment so the connection stays open
                    yield ': keep-alive\n\n'
        finally:
            with _subscribers_lock:
                try:
                    _subscribers.remove(client_q)
                except ValueError:
                    pass
                    
    response = Response(stream_with_context(stream()), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache, no-transform'
    response.headers['Connection'] = 'keep-alive'
    response.headers['X-Accel-Buffering'] = 'no' # Disable Nginx/proxy buffering
    return response

@app.route('/video_feed')
def video_feed():
    def gen():
        global vh
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, 40]  # Low quality = much faster on Pi 4
        while True:
            if vh:
                frame = vh.get_frame()
                if frame is not None:
                    ret, jpeg = cv2.imencode('.jpg', frame, encode_params)
                    if ret:
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
            time.sleep(0.1)  # ~10fps stream — smooth enough for camera preview
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/course-select', methods=['POST'])
def course_select():
    global vi
    data = request.get_json()
    course_name = data.get('course', '')
    
    course = COURSE_DETAILS.get(course_name)
    if not course:
        return jsonify({'error': 'Course not found'}), 404
    
    # Stop any ongoing speech
    if vi:
        vi.stop_speaking()
    
    # Speak in background thread so we don't block the HTTP response
    def speak_course():
        global vi
        if vi:
            speech = f"Let me tell you about {course['title']}. {course['description']}"
            
            def on_ready():
                notify_ui('status', {'state': 'Speaking'})
                notify_ui('message', {'role': 'robot', 'content': speech})
                
            vi.speak(speech, on_ready=on_ready)
            notify_ui('status', {'state': 'Idle'})
    
    threading.Thread(target=speak_course, daemon=True).start()
    
    return jsonify({'status': 'ok'})

def notify_ui(event_type, data):
    """Broadcast an SSE event to all connected browser clients."""
    global _last_status
    if event_type == 'status':
        if _last_status and _last_status.get('state') == data.get('state'):
            time.sleep(0.01) # Still yield GIL briefly
            return # AVOID SPAMMING THE QUEUE
        _last_status = data
        
    event = {'type': event_type, 'data': data}
    with _subscribers_lock:
        for q in list(_subscribers):
            try:
                q.put_nowait(event)
            except queue.Full:
                pass  # Slow client — drop oldest implicitly via maxsize
                
    # CRITICAL FIX: Yield the Python GIL (Global Interpreter Lock) for 10ms.
    # If we don't do this, the main thread will immediately jump into 
    # heavy blocking audio I/O (speech recognition or TTS) and starve
    # the Flask thread, preventing it from sending this SSE event to the UI!
    time.sleep(0.01)

def run_server():
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=False)

def launch_ui():
    """Automatically opens the UI in kiosk mode after a short delay."""
    time.sleep(3) # Wait for server to start
    url = "http://localhost:5000"
    print(f"Launching UI at {url}...")
    
    # Try common Chromium paths for Kiosk mode
    chrome_paths = ['chromium-browser', 'chromium', 'google-chrome']
    for path in chrome_paths:
        try:
            subprocess.Popen([path, '--kiosk', '--app=' + url])
            return # Success
        except Exception:
            continue
            
    # Fallback to default browser
    webbrowser.open(url)

# --- Robotics Logic ---

def main():
    global vi, vh
    print("--- Robotics Chatbot Starting ---")
    
    # Start web server in a separate thread
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Auto-launch the UI browser
    ui_thread = threading.Thread(target=launch_ui, daemon=True)
    ui_thread.start()
    print("Web UI available at http://localhost:5000")

    # Initialize components — ESP32Bridge is shared between servos and motors
    esp32 = ESP32Bridge(port='/dev/ttyUSB0', baudrate=115200)
    sc = ServoController(esp32_bridge=esp32)
    vi = VoiceInterface()
    brain = ChatBrain()
    vh = VisionHandler()
    vh.start()
    # motor commands go through esp32 directly
    motor = esp32  # esp32.set_state('C'), esp32.stop() — same API as MotorBridge

    def signal_handler(sig, frame):
        print("\nExiting and cleaning up...")
        vh.stop()
        sc.cleanup()
        esp32.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    while True:
        try:
            # ── STATE: WELCOME ──────────────────────────────────────────
            # Show welcome screen; wait for someone to come close
            notify_ui('status', {'state': 'Idle'})
            print("State: Welcome — waiting for someone to approach...")
            
            # Resume square patrol exactly where it left off before interacting
            motor.base_resume()
            print("🔄 [Motor] Robot resuming rectangular patrol")
            
            # Register the obstacle callback — fires when ESP32 sends an OBSTACLE alert
            obstacle_event = threading.Event()
            def on_obstacle(dist):
                obstacle_event.set()  # Wake up the patrol loop to check camera
            motor.on_obstacle = on_obstacle

            while True:
                _, _, _, person_nearby = vh.get_status()
                if person_nearby:
                    break

                # Check if ESP32 raised an obstacle alert
                if obstacle_event.is_set():
                    obstacle_event.clear()
                    print("[Patrol] Obstacle detected — checking camera for human...")
                    
                    # Wait up to 1.5s for MediaPipe to get a clean human reading
                    human_confirmed = False
                    for _ in range(6):  # 6 x 0.25s = 1.5s
                        human_detected, _, _, _ = vh.get_status()
                        if human_detected:
                            human_confirmed = True
                            break
                        time.sleep(0.25)
                    
                    if human_confirmed:
                        print("[Patrol] Human confirmed by camera — starting interaction!")
                        motor.base_stop()
                        break  # Exit patrol loop — fall through to CAMERA state
                    else:
                        print("[Patrol] Obstacle is inanimate — pivoting left to resume patrol.")
                        motor.base_resume()  # Tells ESP32 to pivot left and continue the rectangle
                    
                time.sleep(0.3)

            # ── STATE: CAMERA ───────────────────────────────────────────
            # Person is close — show camera + wave prompt; wait for wave
            
            # STOP moving immediately!
            motor.stop()
            print("🛑 [Motor] Robot stopped — person detected nearby")
            
            # Reset any lingering wave from before
            vh.reset_wave()
            notify_ui('status', {'state': 'PersonNearby'})
            print("State: Camera — person nearby, waiting for wave...")

            wave_seen = False
            lost_frames = 0
            wait_loops = 0
            while True:
                human_detected, wave_detected, _, person_nearby = vh.get_status()
                if wave_detected:
                    wave_seen = True
                    break
                    
                # If they walked away before waving → debounce to prevent flickering
                if not human_detected and not person_nearby:
                    lost_frames += 1
                else:
                    lost_frames = 0
                    
                wait_loops += 1
                    
                if lost_frames > 3: # Wait ~1 second (+ 0.75s in vision) = ~1.7s total before reverting
                    print("Person walked away before waving. Back to welcome.")
                    notify_ui('status', {'state': 'Idle'}) # Explicitly tell UI to go back to welcome
                    break
                    
                if wait_loops > 100: # 30 seconds timeout (100 loops * 0.3s)
                    print("Timeout: Person stood in front but didn't wave for 30s. Resuming patrol.")
                    notify_ui('status', {'state': 'Idle'})
                    break
                    
                time.sleep(0.3)

            if not wave_seen:
                # Person left without waving — loop back to welcome
                continue

            # ── STATE: CHAT ─────────────────────────────────────────────
            # Wave detected — send dedicated event so frontend switches screen
            # BEFORE we start speaking (avoids relying on the overloaded 'Speaking' signal)
            notify_ui('chat_start', {})
            greeting = "Welcome to Luminar Technolab! I am your AI receptionist. How can I help you today?"
            # Small pause so the frontend has time to animate the transition
            time.sleep(0.5)
            
            def on_greet_ready():
                notify_ui('status', {'state': 'Speaking'})
                notify_ui('message', {'role': 'robot', 'content': greeting})
                sc.gesture_wave()
                
            # The robot will stay in earlier UI state until TTS file completely finishes downloading
            vi.speak(greeting, on_ready=on_greet_ready)

            while True:
                notify_ui('status', {'state': 'Listening'})
                user_text = vi.listen()

                if not user_text:
                    # Check if human is still present
                    human_detected, _, _, _ = vh.get_status()
                    if not human_detected:
                        print("Vision: Human left. Returning to welcome screen.")
                        farewell = "Goodbye! Have a great day!"
                        
                        def on_farewell_ready():
                            notify_ui('status', {'state': 'Speaking'})
                            notify_ui('message', {'role': 'robot', 'content': farewell})
                            sc.gesture_wave()
                            
                        vi.speak(farewell, on_ready=on_farewell_ready)
                        break
                    continue

                notify_ui('message', {'role': 'user', 'content': user_text})

                if "goodbye" in user_text.lower() or "bye" in user_text.lower() or "exit" in user_text.lower():
                    exit_msg = "Goodbye! Have a nice day. Come visit us again!"
                    
                    def on_exit_ready():
                        notify_ui('status', {'state': 'Speaking'})
                        notify_ui('message', {'role': 'robot', 'content': exit_msg})
                        sc.gesture_wave()
                        
                    vi.speak(exit_msg, on_ready=on_exit_ready)
                    break

                notify_ui('status', {'state': 'Thinking'})
                think_stop = threading.Event()
                think_thread = threading.Thread(
                    target=sc.gesture_thinking, args=(think_stop,), daemon=True
                )
                think_thread.start()
                response = brain.get_response(user_text)
                think_stop.set()
                think_thread.join(timeout=1.0)

                # Set up the on_ready callback — this only fires when the MP3 finishes downloading
                # and is actively beginning playback out of the speakers!
                def on_chat_ready():
                    notify_ui('status', {'state': 'Speaking'})
                    notify_ui('message', {'role': 'robot', 'content': response})
                    estimated_duration = max(1.5, len(response) / 15.0)
                    t = threading.Thread(target=sc.gesture_talking, args=(estimated_duration,), daemon=True)
                    t.start()

                # Synchronous non-interruptable speech
                vi.speak(response, on_ready=on_chat_ready)
                time.sleep(0.5)

            # Chat ended — reset brain memory, clear chat log, go back to welcome
            brain.reset()
            notify_ui('reset', {})
            notify_ui('status', {'state': 'Idle'})
            print("State: Chat ended — returning to welcome screen.")

        except Exception as e:
            print(f"Error in main loop: {e}")
            notify_ui('status', {'state': 'Idle'})
            time.sleep(1)

    sc.cleanup()
    print("Goodbye!")

if __name__ == "__main__":
    main()
