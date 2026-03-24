from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package='reception_robot',
            executable='speech_node',
            name='speech_node'
        ),
        Node(
            package='reception_robot',
            executable='brain_node',
            name='brain_node'
        ),
        Node(
            package='reception_robot',
            executable='servo_node',
            name='servo_node'
        ),
        Node(
            package='reception_robot',
            executable='vision_node',
            name='vision_node'
        ),
        Node(
            package='reception_robot',
            executable='motor_node',
            name='motor_node'
        ),
    ])
