import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import speech_recognition as sr
from gtts import gTTS
import pygame
import os
import time
import threading
import re

class SpeechNode(Node):
    def __init__(self):
        super().__init__('speech_node')
        
        # Audio setup
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        pygame.mixer.init()
        
        # ROS2 Pub/Sub
        self.publisher = self.create_publisher(String, 'user_speech', 10)
        self.subscription = self.create_subscription(
            String, 'robot_response', self.response_callback, 10
        )
        
        # Start listening loop in a background thread
        self.listen_thread = threading.Thread(target=self.listening_loop, daemon=True)
        self.listen_thread.start()
        
        self.get_logger().info("Speech Node Started. Listening for user...")

    def listening_loop(self):
        while rclpy.ok():
            try:
                with self.microphone as source:
                    self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    self.get_logger().info("Listening...")
                    audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                
                text = self.recognizer.recognize_google(audio)
                self.get_logger().info(f"Recognized: {text}")
                
                msg = String()
                msg.data = text
                self.publisher.publish(msg)
                
            except sr.WaitTimeoutError:
                continue
            except Exception as e:
                self.get_logger().warn(f"STT Error: {e}")
                time.sleep(1)

    def response_callback(self, msg):
        text = msg.data
        self.get_logger().info(f"Speaking response...")
        
        # Clean [tags] from speech using robust regex
        speech_text = re.sub(r'\[.*?\]', '', text).strip()
        
        if not speech_text:
            return
        
        try:
            tts = gTTS(text=speech_text, lang='en')
            tts.save("response.mp3")
            
            pygame.mixer.music.load("response.mp3")
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
                
            pygame.mixer.music.unload()
            os.remove("response.mp3")
        except Exception as e:
            self.get_logger().error(f"TTS Error: {e}")

def main(args=None):
    rclpy.init(args=args)
    node = SpeechNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
