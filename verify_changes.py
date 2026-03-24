import os
import sys

# Add current dir to path to import local modules
sys.path.append(os.getcwd())

def test_servos():
    print("--- Testing Servo Configuration ---")
    try:
        from servos import ServoController
        sc = ServoController()
        print(f"Joints configured: {list(sc.pins.keys())}")
        expected_joints = ['L_WRIST', 'L_ELBOW', 'R_WRIST', 'R_ELBOW']
        for joint in expected_joints:
            if joint in sc.pins:
                print(f" [OK] {joint} found")
            else:
                print(f" [FAIL] {joint} missing")
        sc.cleanup()
    except Exception as e:
        print(f" [ERROR] Could not initialize ServoController: {e}")
        print(" (Note: This is expected if RPi.GPIO is not available on this machine)")

def test_brain():
    print("\n--- Testing Brain Connectivity Fallback ---")
    try:
        from brain import ChatBrain
        # Force no API key
        os.environ['GROQ_API_KEY'] = "gsk_invalid_placeholder"
        brain = ChatBrain()
        response = brain.get_response("Hello")
        print(f"Response with no API key: {response}")
        if "internet" in response.lower() or "cloud" in response.lower():
            print(" [OK] Correct fallback message received")
        else:
            print(" [FAIL] Unexpected fallback message")
    except Exception as e:
        print(f" [ERROR] Brain test failed: {e}")

if __name__ == "__main__":
    test_servos()
    test_brain()
