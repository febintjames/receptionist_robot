#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║          RECEPTION ROBOT — LAPTOP TERMINAL TESTER        ║
║                                                          ║
║  Test with or without ESP32 hardware.                    ║
║                                                          ║
║  Usage:                                                  ║
║    python3 test_laptop.py                   (stub mode)  ║
║    python3 test_laptop.py /dev/ttyUSB0      (ESP32 hw)   ║
║    python3 test_laptop.py COM3              (Windows)    ║
╚══════════════════════════════════════════════════════════╝

Keyboard Commands (type + Enter):
  p  → Person detected nearby (robot stops)
  l  → Person left (goes back to patrolling)
  w  → Wave detected (starts conversation)
  u  → Ultrasonic obstacle < 50cm (emergency stop)
  c  → Clear obstacle (resume patrolling)
  t  → Test thinking gesture (3 seconds)
  g  → Test talking gesture (3 seconds)
  v  → Test wave gesture
  s  → Query ESP32 status
  q  → Quit
"""

import sys
import time
import threading
from esp32_bridge import ESP32Bridge
from servos import ServoController


class RobotSimulator:
    def __init__(self, port=None):
        # Connect to ESP32 if port given
        if port:
            self.esp32 = ESP32Bridge(port=port)
        else:
            self.esp32 = ESP32Bridge(port='stub')  # Stub mode

        self.sc = ServoController(esp32_bridge=self.esp32)
        self.state = 'IDLE'
        self.obstacle_active = False
        self.running = True

        # Register obstacle callback
        self.esp32.on_obstacle = self._obstacle_callback

    def _obstacle_callback(self, distance_cm):
        """Called automatically by ESP32Bridge when obstacle detected."""
        if not self.obstacle_active:
            self.obstacle_active = True
            old = self.state
            self.state = 'EMERGENCY_STOP'
            print(f"\n{'='*60}")
            print(f"  ⚠️  AUTO-DETECTED OBSTACLE at {distance_cm}cm!")
            print(f"  STATE: {old} → EMERGENCY_STOP")
            print(f"  (ESP32 has already stopped motors)")
            print(f"  Press 'c' to clear obstacle")
            print(f"{'='*60}")

    def set_state(self, new_state, reason=""):
        old = self.state
        self.state = new_state
        reason_str = f" ({reason})" if reason else ""
        print(f"\n{'='*60}")
        print(f"  STATE: {old} → {new_state}{reason_str}")
        print(f"{'='*60}")

    def start_patrolling(self):
        self.set_state('PATROLLING', 'No one nearby — circling')
        self.esp32.set_state('C')

    def person_nearby(self):
        self.set_state('PERSON_NEARBY', 'Person detected — stopping')
        self.esp32.stop()
        print("  Waiting for wave gesture...")

    def person_left(self):
        self.set_state('IDLE', 'Person walked away')
        self.start_patrolling()

    def wave_detected(self):
        self.set_state('GREETING', 'Wave detected — greeting visitor')
        self.esp32.stop()
        print("  Robot says: 'Welcome to Luminar Technolab!'")
        self.sc.gesture_wave()
        time.sleep(2)
        self.set_state('LISTENING', 'Waiting for visitor to speak')

    def ultrasonic_obstacle(self):
        self.obstacle_active = True
        prev = self.state
        self.set_state('EMERGENCY_STOP', f'Obstacle < 50cm! (was {prev})')
        self.esp32.stop()
        print("  ⚠️  ULTRASONIC SAFETY: All movement halted!")
        print("  Press 'c' to clear obstacle and resume")

    def clear_obstacle(self):
        if not self.obstacle_active:
            print("  No active obstacle to clear.")
            return
        self.obstacle_active = False
        self.set_state('IDLE', 'Obstacle cleared')
        self.start_patrolling()

    def test_thinking(self, duration=3.0):
        self.set_state('THINKING', f'Testing thinking gesture for {duration}s')
        stop_event = threading.Event()
        t = threading.Thread(target=self.sc.gesture_thinking, args=(stop_event,), daemon=True)
        t.start()
        time.sleep(duration)
        stop_event.set()
        t.join(timeout=1.0)
        self.set_state('IDLE', 'Thinking gesture test complete')

    def test_talking(self, duration=3.0):
        self.set_state('SPEAKING', f'Testing talking gesture for {duration}s')
        self.sc.gesture_talking(duration=duration)
        time.sleep(duration + 0.5)
        self.set_state('IDLE', 'Talking gesture test complete')

    def test_wave(self):
        self.set_state('WAVING', 'Testing wave gesture')
        self.sc.gesture_wave()
        time.sleep(3)
        self.set_state('IDLE', 'Wave gesture test complete')

    def query_status(self):
        status = self.esp32.query_status()
        if status:
            print(f"\n  📊 ESP32 Status:")
            print(f"     Base: {'Circling' if status['base'] == 'C' else 'Stopped'}")
            print(f"     L_ELBOW: {status['l_elbow']}°  L_WRIST: {status['l_wrist']}°")
            print(f"     R_ELBOW: {status['r_elbow']}°  R_WRIST: {status['r_wrist']}°")
            print(f"     Ultrasonic: {status['distance']}cm")
        else:
            print("  Could not query status (stub mode or connection issue)")

    def cleanup(self):
        self.running = False
        self.sc.cleanup()
        self.esp32.close()


def main():
    # Check for port argument
    port = sys.argv[1] if len(sys.argv) > 1 else None

    if port:
        print(f"🔌 Connecting to ESP32 on {port}...")
    else:
        print("💻 No port given — running in STUB mode")
        print("   To test with hardware: python3 test_laptop.py /dev/ttyUSB0\n")

    print(__doc__)
    sim = RobotSimulator(port=port)

    sim.start_patrolling()

    print("\nType a command + Enter:")
    print("  p=person nearby  l=person left  w=wave  u=obstacle  c=clear")
    print("  t=thinking  g=talking  v=wave  s=status  q=quit\n")

    while sim.running:
        try:
            cmd = input("> ").strip().lower()
            if not cmd:
                continue

            if cmd == 'q':
                print("\n👋 Shutting down...")
                break
            elif cmd == 'p':
                sim.person_nearby()
            elif cmd == 'l':
                sim.person_left()
            elif cmd == 'w':
                sim.wave_detected()
            elif cmd == 'u':
                sim.ultrasonic_obstacle()
            elif cmd == 'c':
                sim.clear_obstacle()
            elif cmd == 't':
                threading.Thread(target=sim.test_thinking, args=(3.0,), daemon=True).start()
            elif cmd == 'g':
                threading.Thread(target=sim.test_talking, args=(3.0,), daemon=True).start()
            elif cmd == 'v':
                threading.Thread(target=sim.test_wave, daemon=True).start()
            elif cmd == 's':
                sim.query_status()
            else:
                print(f"  Unknown: '{cmd}'. Use p/l/w/u/c/t/g/v/s/q")

        except (KeyboardInterrupt, EOFError):
            print("\n👋 Shutting down...")
            break

    sim.cleanup()
    print("Done.")


if __name__ == '__main__':
    main()
