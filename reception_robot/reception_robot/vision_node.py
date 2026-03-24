import rclpy
from rclpy.node import Node
from std_msgs.msg import Bool, Float32
import sys
import os

# Import VisionHandler from the parent directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from vision import VisionHandler

class VisionNode(Node):
    def __init__(self):
        super().__init__('vision_node')
        
        self.vh = VisionHandler()
        if not self.vh.start():
            self.get_logger().error("Failed to start Vision Handler")
            return
            
        self.person_pub = self.create_publisher(Bool, 'human_detected', 10)
        self.wave_pub = self.create_publisher(Bool, 'wave_detected', 10)
        self.speaker_pub = self.create_publisher(Float32, 'active_speaker_offset', 10)
        
        self.timer = self.create_timer(0.1, self.timer_callback)
        self.get_logger().info("Vision Node Started. Tracking faces and waves.")

    def timer_callback(self):
        detected, waved, offset = self.vh.get_status()
        
        msg_detected = Bool()
        msg_detected.data = detected
        self.person_pub.publish(msg_detected)
        
        msg_waved = Bool()
        msg_waved.data = waved
        self.wave_pub.publish(msg_waved)
        
        msg_offset = Float32()
        msg_offset.data = float(offset)
        self.speaker_pub.publish(msg_offset)

def main(args=None):
    rclpy.init(args=args)
    node = VisionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.vh.stop()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
