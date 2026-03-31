# 🤖 AI Receptionist Robot — Luminar Technolab

An AI-powered reception robot that greets visitors, answers questions about courses, and uses arm gestures + base movement to create a lifelike interaction.

**Brain:** Gemini / Groq LLM  •  **Vision:** OpenCV person detection + wave recognition  •  **Voice:** Edge TTS + Google STT  •  **Body:** ESP32 (4 servos + 2 DC motors + ultrasonic)

---

## ✨ Features

- 🔄 **Idle Patrol** — Robot circles around when no one is nearby
- 🛑 **Person Detection** — Stops moving when someone approaches
- 👋 **Wave Recognition** — Detects hand wave to start interaction
- 🤔 **Thinking Gesture** — Alternating arm motion (one up + wrist right, other down + wrist left) while AI generates response
- 🗣️ **Talking Gesture** — Random arm movements while speaking
- ⚠️ **Ultrasonic Safety** — Emergency stop when obstacle < 50cm
- 💬 **Voice Chat** — Listen, think, speak cycle with interruption support
- 🖥️ **Web UI** — Beautiful touchscreen interface via Flask

---

## 🏗️ Architecture

```
┌──────────────────────┐       USB Serial        ┌───────────────────────┐
│    Raspberry Pi      │◄───────────────────────►│       ESP32           │
│                      │    115200 baud          │                       │
│  • Camera + Vision   │                         │  • 4 Arm Servos       │
│  • Gemini/Groq AI    │    Commands:            │    (L/R Elbow+Wrist)  │
│  • Voice (TTS/STT)   │    C, S, A:..., H, ?   │  • 2 DC Motors (base) │
│  • Flask Web UI      │                         │  • Ultrasonic Sensor  │
│  • State Machine     │    Responses:           │  • Safety Override    │
│                      │    OK, OBSTACLE:xx      │                       │
└──────────────────────┘                         └───────────────────────┘
```

---

## 📁 Project Files

| File | Description |
|------|-------------|
| `main.py` | Main state machine — orchestrates all components |
| `esp32_bridge.py` | Python ↔ ESP32 serial communication bridge |
| `servos.py` | Servo controller with gesture API (thinking, talking, wave) |
| `gemini_brain.py` | Gemini / Groq AI chat backend |
| `voice.py` | Voice interface — Edge TTS + Google Speech Recognition |
| `vision.py` | OpenCV person detection + wave recognition |
| `test_laptop.py` | Terminal-based simulator for testing without hardware |
| `esp32_controller/` | Arduino firmware for ESP32 |
| `ui/` | Web UI (HTML/CSS/JS) served by Flask |

---

## 🚀 Getting Started

### Step 1: Flash the ESP32

1. Open `esp32_controller/esp32_controller.ino` in **Arduino IDE**
2. Install the **ESP32Servo** library:
   - Sketch → Include Library → Manage Libraries → search `ESP32Servo` → Install
3. Select Board: **ESP32 Dev Module**
4. Upload ⬆️

### Step 2: Wire the Hardware

**Arm Servos:**
| Servo | ESP32 GPIO |
|-------|------------|
| Left Elbow | 13 |
| Left Wrist | 14 |
| Right Elbow | 27 |
| Right Wrist | 26 |

**Base Motors (L298N):**
| L298N | ESP32 GPIO |
|-------|------------|
| IN1 | 25 |
| IN2 | 33 |
| IN3 | 32 |
| IN4 | 15 |

**Ultrasonic (HC-SR04):**
| Pin | ESP32 GPIO |
|-----|------------|
| TRIG | 12 |
| ECHO | 4 |

> ⚠️ **Power servos from a separate 5V 2A+ supply**, NOT from ESP32's 5V pin!

### Step 3: Test from Laptop

```bash
# Install dependencies
pip install pyserial

# Find your ESP32 port
ls /dev/ttyUSB*         # Linux
ls /dev/cu.usbserial*   # Mac

# Quick hardware test
python3 esp32_bridge.py /dev/ttyUSB0

# Full interactive simulator
python3 test_laptop.py /dev/ttyUSB0

# Test without hardware (stub mode)
python3 test_laptop.py
```

**Simulator Commands:**
| Key | Action |
|-----|--------|
| `p` | Person nearby → robot stops |
| `l` | Person left → robot circles |
| `t` | Test thinking gesture (alternating arms) |
| `g` | Test talking gesture |
| `v` | Test wave gesture |
| `u` | Simulate obstacle |
| `s` | Query ESP32 status |
| `q` | Quit |

### Step 4: Deploy to Raspberry Pi

```bash
# Copy to Pi
scp -r reception_bot/ pi@<PI_IP>:/home/pi/

# SSH in and run
ssh pi@<PI_IP>
cd /home/pi/reception_bot
pip install -r requirements.txt
python3 main.py
```

---

## 📡 ESP32 Serial Protocol

| Command | Description | Response |
|---------|-------------|----------|
| `C` | Base: circle | `OK` |
| `S` | Base: stop | `OK` |
| `A:LE:110:LW:20:RE:90:RW:40` | Set arm angles | `OK:LE:110:...` |
| `H` | Arms: home | `OK:LE:160:...` |
| `?` | Query status | `STATUS:S:LE:160:LW:70:RE:90:RW:40:D:999` |
| *(auto)* | Obstacle detected | `OBSTACLE:35` |

---

## 🔧 Troubleshooting

| Problem | Fix |
|---------|-----|
| `Permission denied: /dev/ttyUSB0` | `sudo chmod 666 /dev/ttyUSB0` |
| Servos jitter | Use external 5V power, not ESP32's 5V |
| Motors spin wrong way | Swap IN1↔IN2 or IN3↔IN4 wires |
| `OBSTACLE` keeps firing | Check HC-SR04 wiring |

---

## 📋 Requirements

- Python 3.8+
- Raspberry Pi 4 (or laptop for testing)
- ESP32 Dev Board
- 4x Servo motors (SG90 / MG996R)
- L298N Motor Driver + 2 DC motors
- HC-SR04 Ultrasonic Sensor
- USB Camera
- Speaker + Microphone
