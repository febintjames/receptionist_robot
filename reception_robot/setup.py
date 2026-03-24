from setuptools import setup
import os
from glob import glob

package_name = 'reception_robot'

setup(
    name=package_name,
    version='0.0.1',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=False,
    maintainer='akash',
    maintainer_email='akash@example.com',
    description='Robot reception chatbot with servo control and Groq intelligence.',
    license='Apache License 2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'servo_node = reception_robot.servo_node:main',
            'brain_node = reception_robot.brain_node:main',
            'speech_node = reception_robot.speech_node:main',
            'motor_node = reception_robot.motor_node:main',
            'vision_node = reception_robot.vision_node:main',
        ],
    },
)
