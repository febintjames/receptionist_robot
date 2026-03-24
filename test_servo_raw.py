import RPi.GPIO as GPIO
import time
import sys

# Change this pin to test a single servo (e.g., L_WRIST=17, L_ELBOW=18, R_WRIST=27, R_ELBOW=22)
TEST_PIN = 17 

def test_servo():
    print(f"Testing bare-metal PWM on GPIO {TEST_PIN}...")
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(TEST_PIN, GPIO.OUT)
        
        # 50Hz = 20ms period
        pwm = GPIO.PWM(TEST_PIN, 50)
        
        # Start at exactly 90 degrees (1.5ms pulse)
        # Duty cycle = (1.5ms / 20ms) * 100 = 7.5%
        print("Moving to 90 degrees (Center)...")
        pwm.start(7.5)
        time.sleep(2)
        
        # Move to 0 degrees (1.0ms pulse)
        # Duty cycle = (1.0ms / 20ms) * 100 = 5.0%
        print("Moving to 0 degrees (Min)...")
        pwm.ChangeDutyCycle(5.0)
        time.sleep(2)
        
        # Move to 180 degrees (2.0ms pulse)
        # Duty cycle = (2.0ms / 20ms) * 100 = 10.0%
        print("Moving to 180 degrees (Max)...")
        pwm.ChangeDutyCycle(10.0)
        time.sleep(2)
        
        # Back to center
        print("Moving back to Center...")
        pwm.ChangeDutyCycle(7.5)
        time.sleep(1)
        
        print("Test complete. Hardware PWM is working.")
        
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        print("If you see an error about /dev/gpiomem or /dev/mem, run this script with 'sudo'.")
        print("If you see 'This module can only be run on a Raspberry Pi!', "
              "make sure you are running this ON THE RASPBERRY PI, not your laptop!")
    finally:
        if 'pwm' in locals():
            pwm.stop()
        GPIO.cleanup()

if __name__ == "__main__":
    test_servo()
