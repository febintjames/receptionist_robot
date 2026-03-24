from std_msgs.msg import String, Bool, Float32
from geometry_msgs.msg import Twist
from groq import Groq
import os
import time
import threading

class BrainNode(Node):
    def __init__(self):
        super().__init__('brain_node')
        
        # API Setup
        self.api_key = os.environ.get("GROQ_API_KEY") or "gsk_..."
        self.client = Groq(api_key=self.api_key) if self.api_key else None
        self.model = "llama-3.3-70b-versatile"
        
        # ROS2 Pub/Sub
        self.speech_sub = self.create_subscription(String, 'user_speech', self.speech_callback, 10)
        self.person_sub = self.create_subscription(Bool, 'human_detected', self.person_callback, 10)
        self.wave_sub = self.create_subscription(Bool, 'wave_detected', self.wave_callback, 10)
        self.speaker_sub = self.create_subscription(Float32, 'active_speaker_offset', self.speaker_callback, 10)
        
        self.response_pub = self.create_publisher(String, 'robot_response', 10)
        self.cmd_vel_pub = self.create_publisher(Twist, 'cmd_vel', 10)
        
        # Robot State
        self.state = "IDLE" # IDLE, NAVIGATING, TALKING
        self.human_present = False
        self.wave_received = False
        self.speaker_offset = 0.0
        
        # System Prompt
        self.system_prompt = (
            "You are the AI Receptionist for Luminar Technolab. Be professional and friendly. "
            "Use [waves] for greetings."
        )
        
        # Timer for behavior logic
        self.timer = self.create_timer(0.5, self.behavior_loop)
        self.get_logger().info("Brain Node Started with Nav/Vision integration.")

    def person_callback(self, msg):
        self.human_present = msg.data

    def wave_callback(self, msg):
        if msg.data and not self.wave_received:
            self.get_logger().info("Wave detected! Initiating interaction.")
            self.wave_received = True

    def speaker_callback(self, msg):
        self.speaker_offset = msg.data

    def speech_callback(self, msg):
        if self.state == "TALKING" or self.wave_received:
            user_input = msg.data
            self.generate_response(user_input)

    def behavior_loop(self):
        if self.human_present:
            # Stop moving if someone is there
            self.stop_robot()
            
            if self.wave_received:
                self.state = "TALKING"
                # If talking, turn to face speaker
                self.face_speaker()
            else:
                self.state = "IDLE"
        else:
            # No humans, do nothing (teleop mode)
            self.wave_received = False
            self.state = "IDLE"

    def face_speaker(self):
        """Rotate towards the active speaker offset."""
        if abs(self.speaker_offset) > 0.1:
            msg = Twist()
            # P-controller for rotation
            msg.angular.z = -self.speaker_offset * 1.5
            self.cmd_vel_pub.publish(msg)

    def stop_robot(self):
        msg = Twist()
        self.cmd_vel_pub.publish(msg)

    def generate_response(self, text):
        if not self.client: return
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.7,
                max_tokens=256
            )
            response = completion.choices[0].message.content
            out_msg = String()
            out_msg.data = response
            self.response_pub.publish(out_msg)
        except Exception as e:
            self.get_logger().error(f"Chat error: {e}")

def main(args=None):
    rclpy.init(args=args)
    node = BrainNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
