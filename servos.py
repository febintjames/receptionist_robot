try:
    import RPi.GPIO as GPIO
    _GPIO_AVAILABLE = True
except ImportError:
    _GPIO_AVAILABLE = False
    print("RPi.GPIO not found — running without servo hardware (laptop mode)")
import time
import threading

class ServoController:
    def __init__(self):
        if not _GPIO_AVAILABLE:
            self.connected = False
            self.running = False
            self.pins = {}
            return

        # GPIO Mode (BCM)
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        
        # GPIO Pins
        self.pins = {
            'L_WRIST': 17,
            'L_ELBOW': 18,
            'R_WRIST': 27,
            'R_ELBOW': 22
        }
        
        # Define home (neutral) angles and safe limits for each joint
        # Adjust these values to match your specific robot build
        self.HOME_ANGLES = {
            'L_WRIST': 70.0,
            'L_ELBOW': 160.0,
            'R_WRIST': 40.0,
            'R_ELBOW': 90.0
        }
        self.MIN_ANGLES = {
            'L_WRIST': 70.0,
            'L_ELBOW': 160.0,
            'R_WRIST': 40.0,
            'R_ELBOW': 90.0
        }
        self.MAX_ANGLES = {
            'L_WRIST': 20.0,
            'L_ELBOW': 110.0,
            'R_WRIST': 70.0,
            'R_ELBOW': 145.0
        }
        
        # Current and target angles for smooth movement
        self.current_angles = {joint: self.HOME_ANGLES[joint] for joint in self.pins}
        self.target_angles = {joint: self.HOME_ANGLES[joint] for joint in self.pins}
        
        # PWM Setup
        self.pwms = {}
        self.frequency = 50  # 50Hz for servos
        
        # Calibration (Duty Cycle: 2.5 = 0 deg, 12.5 = 180 deg for 50Hz)
        self.min_dc = 2.5
        self.max_dc = 12.5
        
        try:
            for joint, pin in self.pins.items():
                GPIO.setup(pin, GPIO.OUT)
                pwm = GPIO.PWM(pin, self.frequency)
                pwm.start(0)  # Start with 0 duty cycle
                self.pwms[joint] = pwm
            self.connected = True
            
            # Explicitly force the hardware to the defined HOME_ANGLES at boot.
            for joint in self.pins:
                self._apply_angle(joint, self.HOME_ANGLES[joint])
                
        except Exception as e:
            print(f"GPIO Setup Error: {e}")
            self.connected = False
        
        # Initialize to neutral
        if self.connected:
            self.move_to_neutral()
            
        # Start smoothing thread
        self.running = True
        self.smoothing_thread = threading.Thread(target=self._smooth_move_loop, daemon=True)
        self.smoothing_thread.start()

    def _smooth_move_loop(self):
        """Background loop to interpolate towards target angles."""
        while self.running:
            if self.connected:
                moved = False
                for joint in self.pins:
                    diff = self.target_angles[joint] - self.current_angles[joint]
                    if abs(diff) > 0.5:
                        # Smooth adjustment
                        step = max(-5.0, min(5.0, diff * 0.2))
                        self.current_angles[joint] += step
                        self._apply_angle(joint, self.current_angles[joint])
                        moved = True
                if not moved:
                    time.sleep(0.05)
                else:
                    time.sleep(0.02)
            else:
                time.sleep(0.1)

    def _apply_angle(self, joint, angle):
        """Immediately applies angle to hardware."""
        dc = self.min_dc + (angle / 180.0) * (self.max_dc - self.min_dc)
        self.pwms[joint].ChangeDutyCycle(dc)

    def angle_to_duty_cycle(self, angle):
        """Maps 0-180 degrees to duty cycle (2.5 to 12.5)."""
        return self.min_dc + (angle / 180.0) * (self.max_dc - self.min_dc)

    def set_angle(self, joint, angle):
        """Sets target angle for smooth movement, constrained by defined limits."""
        if not self.connected or joint not in self.pins: return
        lower_bound = min(self.MIN_ANGLES[joint], self.MAX_ANGLES[joint])
        upper_bound = max(self.MIN_ANGLES[joint], self.MAX_ANGLES[joint])
        self.target_angles[joint] = max(lower_bound, min(upper_bound, angle))

    def move_to_neutral(self):
        """Sets all joints to their defined home angles."""
        for joint in self.pins:
            self.set_angle(joint, self.HOME_ANGLES[joint])

    def gesture_wave(self):
        """Performs a simple waving gesture."""
        if not self.connected: return
        
        def wave():
            # Lift right arm
            self.set_angle('R_WRIST', 150)
            time.sleep(0.5)
            # Wave elbow
            for _ in range(3):
                self.set_angle('R_ELBOW', 60)
                time.sleep(0.4)
                self.set_angle('R_ELBOW', 120)
                time.sleep(0.4)
            self.move_to_neutral()
            
        threading.Thread(target=wave).start()

    def gesture_talking(self, duration=2.0):
        """Moves arms randomly to simulate talking gestures."""
        if not self.connected: return
        
        import random
        def talk():
            end_time = time.time() + duration
            while time.time() < end_time:
                joint = random.choice(list(self.pins.keys()))
                # Subtle organic movements upwards from home position
                base = self.HOME_ANGLES[joint]
                # Swing upwards from home (0 to +50 degrees) since home is the minimum
                angle = base + random.randint(0, 50)
                self.set_angle(joint, angle)
                time.sleep(random.uniform(0.3, 0.6))
            self.move_to_neutral()
            
        threading.Thread(target=talk).start()

    def cleanup(self):
        """Releases GPIO resources."""
        self.running = False
        if hasattr(self, 'smoothing_thread'):
            self.smoothing_thread.join(timeout=1.0)
        if self.connected:
            for pwm in self.pwms.values():
                pwm.stop()
            GPIO.cleanup()

if __name__ == "__main__":
    # Test script
    sc = ServoController()
    try:
        print("Testing Wave...")
        sc.gesture_wave()
        time.sleep(3)
        print("Testing Talking Gestures...")
        sc.gesture_talking(duration=3)
        time.sleep(4)
    finally:
        sc.cleanup()
