import serial
import time
import threading

class MotorBridge:
    def __init__(self, port='/dev/ttyUSB0', baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.connected = False
        
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)
            self.connected = True
            print(f"[MotorBridge] Connected to ESP32 on {self.port}")
            # Wait for ESP32 to reboot after serial connection
            time.sleep(2)
        except Exception as e:
            print(f"[MotorBridge] Warning: Could not connect to ESP32: {e}")
            print("[MotorBridge] Running in stub mode (No actual movement)")
            
    def set_state(self, state_char):
        """
        Send a state command to the ESP32.
        'C' = Circle
        'S' = Stop
        """
        if state_char not in ['C', 'S']:
            print(f"[MotorBridge] Invalid command: {state_char}")
            return
            
        if self.connected and self.ser:
            try:
                # Send command over Serial
                self.ser.write(state_char.encode('utf-8'))
                self.ser.flush()
                # print(f"[MotorBridge] Sent: {state_char}")
            except Exception as e:
                print(f"[MotorBridge] Serial write error: {e}")
                self.connected = False
        else:
            # Stub mode (when ESP32 is unplugged during testing)
            if state_char == 'C':
                pass # print("[Mock Motor] 🔄 Circling...")
            elif state_char == 'S':
                pass # print("[Mock Motor] 🛑 Stopping...")

    def stop(self):
        """Convenience function to force stop"""
        self.set_state('S')
        
    def close(self):
        if self.ser and self.connected:
            self.stop()
            self.ser.close()
            print("[MotorBridge] Connection closed.")
            
if __name__ == '__main__':
    # Simple test
    bridge = MotorBridge()
    print("Testing Circle for 3 seconds...")
    bridge.set_state('C')
    time.sleep(3)
    print("Stopping.")
    bridge.stop()
    bridge.close()
