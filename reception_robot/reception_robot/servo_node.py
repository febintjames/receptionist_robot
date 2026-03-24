import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import RPi.GPIO as GPIO
import time
import threading
import random
import re

class ServoNode(Node):
    def __init__(self):
        super().__init__('servo_node')
        
        # ROS2 Subscriber for responses (to trigger gestures)
        self.subscription = self.create_subscription(
            String,
            'robot_response',
            self.response_callback,
            10)
            
        # GPIO Mode (BCM)
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
            
        # GPIO Pins (BCM)
        self.pins = {
            'L_WRIST': 17, 'L_ELBOW': 18,
            'R_WRIST': 27, 'R_ELBOW': 22
        }
        
        # Define home (neutral) angles and safe limits for each joint
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
        
        # Setup PWM
        self.pwms = {}
        self.frequency = 50
        
        # PWM duty cycle calibration
        self.min_dc = 2.5
        self.max_dc = 12.5
        
        try:
            for joint, pin in self.pins.items():
                GPIO.setup(pin, GPIO.OUT)
                pwm = GPIO.PWM(pin, self.frequency)
                pwm.start(0)
                self.pwms[joint] = pwm
            self.connected = True
            
            # Explicitly force the hardware to the defined HOME_ANGLES at boot.
            # Without this, the PWM signal stays at 0 (limp) until an animation triggers.
            for joint in self.pins:
                self._apply_angle(joint, self.HOME_ANGLES[joint])
                
            self.get_logger().info("Servo Node Started and Connected to hardware.")
        except Exception as e:
            self.get_logger().error(f"GPIO Setup Error: {e}")
            self.connected = False
        
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
                        # Move max 5 degrees per step for smoothness
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

    def set_angle(self, joint, angle):
        """Sets target angle for smooth movement, constrained by defined limits."""
        if not self.connected or joint not in self.pins: return
        # Calculate true lower and upper bounds dynamically to safely support inverted min/max settings
        lower_bound = min(self.MIN_ANGLES[joint], self.MAX_ANGLES[joint])
        upper_bound = max(self.MIN_ANGLES[joint], self.MAX_ANGLES[joint])
        self.target_angles[joint] = max(lower_bound, min(upper_bound, angle))

    def move_to_neutral(self):
        for joint in self.pins:
            self.set_angle(joint, self.HOME_ANGLES[joint])

    def gesture_talking(self, duration):
        end_time = time.time() + duration
        while time.time() < end_time:
            joint = random.choice(list(self.pins.keys()))
            base = self.HOME_ANGLES[joint]
            max_bound = self.MAX_ANGLES[joint]
            
            # Dynamically swing 0 to 40 degrees towards the MAX_ANGLES bound
            if max_bound >= base:
                swing = random.randint(0, min(40, int(max_bound - base)))
                angle = base + swing
            else:
                swing = random.randint(0, min(40, int(base - max_bound)))
                angle = base - swing
                
            self.set_angle(joint, angle)
            time.sleep(random.uniform(0.3, 0.6))
        self.move_to_neutral()

    def gesture_wave(self):
        # Raise wrist fully
        self.set_angle('R_WRIST', self.MAX_ANGLES['R_WRIST'])
        time.sleep(0.5)
        
        # Wave elbow by alternating between home and a point 60% towards max
        elbow_home = self.HOME_ANGLES['R_ELBOW']
        elbow_max = self.MAX_ANGLES['R_ELBOW']
        wave_pos = elbow_home + ((elbow_max - elbow_home) * 0.6)
        
        for _ in range(3):
            self.set_angle('R_ELBOW', elbow_home)
            time.sleep(0.4)
            self.set_angle('R_ELBOW', wave_pos)
            time.sleep(0.4)
            
        self.move_to_neutral()

    def response_callback(self, msg):
        text = msg.data.lower()
        self.get_logger().info(f"Received text for gesture: {text[:50]}...")
        
        # Check for specific gesture triggers in text
        if '[waves]' in text or 'hello' in text or 'welcome' in text:
            threading.Thread(target=self.gesture_wave).start()
        else:
            # Default talk animation based on sentence length
            duration = max(2.0, len(text) / 12.0)
            threading.Thread(target=self.gesture_talking, args=(duration,)).start()

    def cleanup(self):
        self.running = False
        if hasattr(self, 'smoothing_thread'):
            self.smoothing_thread.join(timeout=1.0)
        if self.connected:
            for pwm in self.pwms.values():
                pwm.stop()
            GPIO.cleanup()

def main(args=None):
    rclpy.init(args=args)
    node = ServoNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.move_to_neutral()
        node.cleanup()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
