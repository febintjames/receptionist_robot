"""
ESP32 Bridge — Unified serial communication with ESP32.
Handles both arm servos and base motors through one serial connection.

Protocol:
  C              → Base: circle
  S              → Base: stop
  A:LE:110:LW:20:RE:90:RW:40  → Set arm angles
  H              → Arms: home position
  ?              → Query status

Responses from ESP32:
  OK             → Success
  OBSTACLE:35    → Obstacle detected at 35cm
  STATUS:S:LE:160:LW:70:RE:90:RW:40:D:999  → Full status
"""

import serial
import time
import threading


class ESP32Bridge:
    def __init__(self, port='/dev/ttyUSB0', baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.connected = False
        self._lock = threading.Lock()
        
        # Obstacle detection callback
        self.on_obstacle = None  # Set externally: fn(distance_cm)
        self._reader_thread = None
        self._running = False
        
        # Last known state
        self.last_distance = 999
        self.obstacle_active = False
        
        # Skip connection for non-real ports (stub mode)
        if port in ('/dev/null', 'null', 'none', 'stub'):
            print("[ESP32] Running in STUB mode (no hardware)")
            return

        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1, write_timeout=1)
            # Disable hardware flow control lines to prevent write buffers from hanging on Linux
            self.ser.dtr = False
            self.ser.rts = False
            
            self.connected = True
            print(f"[ESP32] Connected on {self.port}")
            # Wait for ESP32 reboot after serial connection
            time.sleep(2)
            # Read the READY message
            self._flush_boot()
            # Start background reader for obstacle alerts
            self._running = True
            self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._reader_thread.start()
        except Exception as e:
            print(f"[ESP32] Warning: Could not connect: {e}")
            print("[ESP32] Running in STUB mode (no hardware)")

    def _flush_boot(self):
        """Read any boot messages from ESP32."""
        if not self.connected:
            return
        
        # Disable blocking on readline just for boot flush
        old_timeout = self.ser.timeout
        self.ser.timeout = 0.1
        
        end_time = time.time() + 2
        while time.time() < end_time:
            try:
                if self.ser.in_waiting > 0:
                    line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        print(f"[ESP32 boot] {line}")
                        if line == "READY":
                            print("[ESP32] ✅ Firmware ready!")
                            break
                else:
                    time.sleep(0.05)
            except Exception:
                pass
                
        # Restore timeout
        self.ser.timeout = old_timeout

    def _read_loop(self):
        """Background reader — picks up OBSTACLE alerts from ESP32.
        Uses the same lock as _send() so the two never race on readline()."""
        while self._running and self.connected:
            try:
                # Only try to read if the send path isn't mid-transaction
                with self._lock:
                    if self.ser and self.ser.in_waiting > 0:
                        line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    else:
                        line = ""
                if line.startswith("OBSTACLE:"):
                    try:
                        dist = int(line.split(":")[1])
                        self.last_distance = dist
                        self.obstacle_active = True
                        print(f"[ESP32] ⚠️  OBSTACLE at {dist}cm — motors stopped!")
                        if self.on_obstacle:
                            self.on_obstacle(dist)
                    except (ValueError, IndexError):
                        pass
                elif line and not line.startswith("OK") and not line.startswith("STATUS"):
                    print(f"[ESP32] {line}")
                time.sleep(0.05)
            except Exception as e:
                if self._running:
                    print(f"[ESP32] Read error: {e}")
                time.sleep(0.1)

    def _send(self, command):
        """Send a command to ESP32 and return the response.
        Holds the lock for the entire write+readline so _read_loop cannot
        interleave and steal the OK/STATUS response."""
        if not self.connected:
            print(f"[ESP32 stub] → {command}")
            return "OK"
        
        with self._lock:
            try:
                self.ser.write(f"{command}\n".encode('utf-8'))
                self.ser.flush()
                # Wait for response; ESP32 always replies within ~100 ms
                deadline = time.time() + 1.0
                while time.time() < deadline:
                    if self.ser.in_waiting > 0:
                        response = self.ser.readline().decode('utf-8', errors='ignore').strip()
                        # If we accidentally read an OBSTACLE alert here, handle it
                        # and keep waiting for the command's own response.
                        if response.startswith("OBSTACLE:"):
                            try:
                                dist = int(response.split(":")[1])
                                self.last_distance = dist
                                self.obstacle_active = True
                                print(f"[ESP32] ⚠️  OBSTACLE at {dist}cm (captured in send)")
                                if self.on_obstacle:
                                    threading.Thread(
                                        target=self.on_obstacle, args=(dist,), daemon=True
                                    ).start()
                            except (ValueError, IndexError):
                                pass
                            continue  # wait for the real OK/STATUS
                        return response
                    time.sleep(0.01)
                return ""  # timeout
            except Exception as e:
                print(f"[ESP32] Send error: {e}")
                return ""

    # ── Base Motor Commands ──────────────────────────────────────

    def base_circle(self):
        """Start circular movement."""
        return self._send("C")

    def base_stop(self):
        """Stop base motors."""
        return self._send("S")

    def base_resume(self):
        """Tell ESP32 to skip the obstacle and continue patrol with a left pivot.
        Use this when the camera confirms the obstacle is NOT a human."""
        self.obstacle_active = False
        return self._send("RESUME")

    # Legacy MotorBridge compatibility
    def set_state(self, state_char):
        if state_char == 'C':
            return self.base_circle()
        elif state_char == 'S':
            return self.base_stop()

    def stop(self):
        return self.base_stop()

    # ── Arm Servo Commands ───────────────────────────────────────

    def set_arm_angles(self, l_elbow=None, l_wrist=None, r_elbow=None, r_wrist=None):
        """Set one or more arm servo angles. Only sends specified angles."""
        parts = ["A"]
        if l_elbow is not None:
            parts.append(f"LE:{int(l_elbow)}")
        if l_wrist is not None:
            parts.append(f"LW:{int(l_wrist)}")
        if r_elbow is not None:
            parts.append(f"RE:{int(r_elbow)}")
        if r_wrist is not None:
            parts.append(f"RW:{int(r_wrist)}")
        
        if len(parts) == 1:
            return  # Nothing to send
        
        cmd = ":".join(parts)
        return self._send(cmd)

    def arms_home(self):
        """Send all arms to home position."""
        return self._send("H")

    # ── Status Query ─────────────────────────────────────────────

    def query_status(self):
        """Query ESP32 for full status.
        Returns dict: {base, l_elbow, l_wrist, r_elbow, r_wrist, distance}
        """
        resp = self._send("?")
        if resp.startswith("STATUS:"):
            # Parse: STATUS:S:LE:160:LW:70:RE:90:RW:40:D:999
            parts = resp.split(":")
            try:
                return {
                    'base': parts[1],
                    'l_elbow': int(parts[3]),
                    'l_wrist': int(parts[5]),
                    'r_elbow': int(parts[7]),
                    'r_wrist': int(parts[9]),
                    'distance': int(parts[11])
                }
            except (IndexError, ValueError):
                pass
        return None

    # ── Cleanup ──────────────────────────────────────────────────

    def close(self):
        self._running = False
        if self.connected and self.ser:
            try:
                self.base_stop()
                self.arms_home()
                time.sleep(0.3)
                self.ser.close()
            except Exception:
                pass
            print("[ESP32] Connection closed.")


# ═══════════════════════════════════════════════════════════════════
#  Quick Test
# ═══════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    import sys
    
    port = sys.argv[1] if len(sys.argv) > 1 else '/dev/ttyUSB0'
    print(f"Connecting to ESP32 on {port}...")
    bridge = ESP32Bridge(port=port, baudrate=115200)
    
    if not bridge.connected:
        print("Not connected — running in stub mode for demo")
    
    print("\n--- Quick Hardware Test ---")
    print("1. Query status...")
    status = bridge.query_status()
    print(f"   Status: {status}")
    
    print("2. Arms home...")
    bridge.arms_home()
    time.sleep(1)
    
    print("3. Left arm UP + wrist RIGHT...")
    bridge.set_arm_angles(l_elbow=110, l_wrist=20)
    time.sleep(1)
    
    print("4. Right arm UP + wrist RIGHT...")
    bridge.set_arm_angles(r_elbow=145, r_wrist=70)
    time.sleep(1)
    
    print("5. Arms home...")
    bridge.arms_home()
    time.sleep(1)
    
    print("6. Base circle for 2 seconds...")
    bridge.base_circle()
    time.sleep(2)
    
    print("7. Base stop...")
    bridge.base_stop()
    time.sleep(0.5)
    
    print("8. Final status check...")
    status = bridge.query_status()
    print(f"   Status: {status}")
    
    bridge.close()
    print("Done! ✅")
