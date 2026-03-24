import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist, TransformStamped, Quaternion
from nav_msgs.msg import Odometry
import RPi.GPIO as GPIO
import time
import math
from tf2_ros import TransformBroadcaster

class MotorNode(Node):
    def __init__(self):
        super().__init__('motor_node')
        
        # Configuration (BCM Pins)
        self.declare_parameter('l_pwm_pin', 13)
        self.declare_parameter('l_in1_pin', 19)
        self.declare_parameter('l_in2_pin', 26)
        self.declare_parameter('r_pwm_pin', 12)
        self.declare_parameter('r_in1_pin', 16)
        self.declare_parameter('r_in2_pin', 20)
        
        self.l_pwm_pin = self.get_parameter('l_pwm_pin').value
        self.l_in1_pin = self.get_parameter('l_in1_pin').value
        self.l_in2_pin = self.get_parameter('l_in2_pin').value
        self.r_pwm_pin = self.get_parameter('r_pwm_pin').value
        self.r_in1_pin = self.get_parameter('r_in1_pin').value
        self.r_in2_pin = self.get_parameter('r_in2_pin').value

        # Robot physical parameters (approximate)
        self.wheel_base = 0.2  # meters
        
        # State
        self.x = 0.0
        self.y = 0.0
        self.th = 0.0
        self.last_time = self.get_clock().now()
        self.linear_vel = 0.0
        self.angular_vel = 0.0

        # Setup GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for pin in [self.l_pwm_pin, self.l_in1_pin, self.l_in2_pin, 
                    self.r_pwm_pin, self.r_in1_pin, self.r_in2_pin]:
            GPIO.setup(pin, GPIO.OUT)
            
        self.l_pwm = GPIO.PWM(self.l_pwm_pin, 1000)
        self.r_pwm = GPIO.PWM(self.r_pwm_pin, 1000)
        self.l_pwm.start(0)
        self.r_pwm.start(0)
        
        # Publishers & Broadcasters
        self.odom_pub = self.create_publisher(Odometry, 'odom', 10)
        self.tf_broadcaster = TransformBroadcaster(self)
        
        # Subscription
        self.subscription = self.create_subscription(
            Twist,
            'cmd_vel',
            self.cmd_vel_callback,
            10)
            
        # Timer for Odom (20Hz)
        self.timer = self.create_timer(0.05, self.update_odometry)
        
        self.get_logger().info("Motor Node Started with Odometry. Listening to /cmd_vel")

    def cmd_vel_callback(self, msg):
        self.linear_vel = msg.linear.x
        self.angular_vel = msg.angular.z
        
        l_speed = self.linear_vel - self.angular_vel
        r_speed = self.linear_vel + self.angular_vel
        
        self._set_motor(self.l_pwm, self.l_in1_pin, self.l_in2_pin, l_speed)
        self._set_motor(self.r_pwm, self.r_in1_pin, self.r_in2_pin, r_speed)

    def update_odometry(self):
        current_time = self.get_clock().now()
        dt = (current_time - self.last_time).nanoseconds / 1e9
        self.last_time = current_time

        # Calculate position change
        delta_x = (self.linear_vel * math.cos(self.th)) * dt
        delta_y = (self.linear_vel * math.sin(self.th)) * dt
        delta_th = self.angular_vel * dt

        self.x += delta_x
        self.y += delta_y
        self.th += delta_th

        # Create Quaternion from yaw
        q = self._euler_to_quaternion(0, 0, self.th)

        # Publish TF
        t = TransformStamped()
        t.header.stamp = current_time.to_msg()
        t.header.frame_id = 'odom'
        t.child_frame_id = 'base_link'
        t.transform.translation.x = self.x
        t.transform.translation.y = self.y
        t.transform.translation.z = 0.0
        t.transform.rotation = q
        self.tf_broadcaster.sendTransform(t)

        # Publish Odom message
        odom = Odometry()
        odom.header.stamp = current_time.to_msg()
        odom.header.frame_id = 'odom'
        odom.child_frame_id = 'base_link'
        odom.pose.pose.position.x = self.x
        odom.pose.pose.position.y = self.y
        odom.pose.pose.orientation = q
        odom.twist.twist.linear.x = self.linear_vel
        odom.twist.twist.angular.z = self.angular_vel
        self.odom_pub.publish(odom)

    def _euler_to_quaternion(self, roll, pitch, yaw):
        qx = math.sin(roll/2) * math.cos(pitch/2) * math.cos(yaw/2) - math.cos(roll/2) * math.sin(pitch/2) * math.sin(yaw/2)
        qy = math.cos(roll/2) * math.sin(pitch/2) * math.cos(yaw/2) + math.sin(roll/2) * math.cos(pitch/2) * math.sin(yaw/2)
        qz = math.cos(roll/2) * math.cos(pitch/2) * math.sin(yaw/2) - math.sin(roll/2) * math.sin(pitch/2) * math.cos(yaw/2)
        qw = math.cos(roll/2) * math.cos(pitch/2) * math.cos(yaw/2) + math.sin(roll/2) * math.sin(pitch/2) * math.sin(yaw/2)
        return Quaternion(x=qx, y=qy, z=qz, w=qw)

    def _set_motor(self, pwm, in1, in2, speed):
        duty_cycle = min(100, max(0, abs(speed) * 100))
        if speed > 0:
            GPIO.output(in1, GPIO.HIGH)
            GPIO.output(in2, GPIO.LOW)
        elif speed < 0:
            GPIO.output(in1, GPIO.LOW)
            GPIO.output(in2, GPIO.HIGH)
        else:
            GPIO.output(in1, GPIO.LOW)
            GPIO.output(in2, GPIO.LOW)
            duty_cycle = 0
        pwm.ChangeDutyCycle(duty_cycle)

    def stop(self):
        self.l_pwm.ChangeDutyCycle(0)
        self.r_pwm.ChangeDutyCycle(0)
        GPIO.output(self.l_in1_pin, GPIO.LOW)
        GPIO.output(self.l_in2_pin, GPIO.LOW)
        GPIO.output(self.r_in1_pin, GPIO.LOW)
        GPIO.output(self.r_in2_pin, GPIO.LOW)

def main(args=None):
    rclpy.init(args=args)
    node = MotorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop()
        GPIO.cleanup()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
