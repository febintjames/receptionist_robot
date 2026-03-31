// ═══════════════════════════════════════════════════════════════
//  ESP32 Unified Controller — Receptionist Robot
//  Controls: 4 arm servos + 2 base DC motors + ultrasonic sensor
//  
//  Serial Protocol (115200 baud):
//  ─────────────────────────────────────────────────────────
//  COMMANDS (Laptop/Pi → ESP32):
//    C              → Base: circle
//    S              → Base: stop
//    A:LE:110:LW:20:RE:90:RW:40  → Set all 4 servo angles
//    H              → Arms: go to home position
//    ?              → Query: returns status line
//
//  RESPONSES (ESP32 → Laptop/Pi):
//    OK             → Command executed
//    OK:LE:110:LW:20:RE:90:RW:40  → Current angles after arm cmd
//    OBSTACLE:35    → Obstacle at 35cm, motors forced stop
//    STATUS:S:LE:160:LW:70:RE:90:RW:40:D:999  → Full status
//    READY          → Boot complete
// ═══════════════════════════════════════════════════════════════

#include <ESP32Servo.h>

// ── Pin Definitions ─────────────────────────────────────────────

// Arm Servos (use any PWM-capable GPIO)
#define PIN_L_ELBOW  13
#define PIN_L_WRIST  14
#define PIN_R_ELBOW  27
#define PIN_R_WRIST  26

// L298N Motor Driver (base wheels)
#define PIN_IN1  25
#define PIN_IN2  33
#define PIN_IN3  32
#define PIN_IN4  15

// Ultrasonic Sensor
#define PIN_TRIG  12
#define PIN_ECHO  4

// ── Safety Threshold ────────────────────────────────────────────
#define OBSTACLE_DISTANCE_CM  50   // Stop base motors if closer than this

// ── Servo Objects ───────────────────────────────────────────────
Servo servoLE;  // Left Elbow
Servo servoLW;  // Left Wrist
Servo servoRE;  // Right Elbow
Servo servoRW;  // Right Wrist

// ── Home Angles (match servos.py) ───────────────────────────────
const int HOME_LE = 160;
const int HOME_LW = 70;
const int HOME_RE = 90;
const int HOME_RW = 40;

// ── Current Target Angles ───────────────────────────────────────
int targetLE = HOME_LE;
int targetLW = HOME_LW;
int targetRE = HOME_RE;
int targetRW = HOME_RW;

// ── Current Actual Angles (for smooth movement) ─────────────────
float currentLE = HOME_LE;
float currentLW = HOME_LW;
float currentRE = HOME_RE;
float currentRW = HOME_RW;

// ── Base State ──────────────────────────────────────────────────
char baseState = 'S';  // 'S' = Stop, 'C' = Circle
bool obstacleActive = false;
long lastDistance = 999;

// ── Serial Buffer ───────────────────────────────────────────────
String serialBuffer = "";

// ═════════════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);

  // Ultrasonic
  pinMode(PIN_TRIG, OUTPUT);
  pinMode(PIN_ECHO, INPUT);

  // Motor pins
  pinMode(PIN_IN1, OUTPUT);
  pinMode(PIN_IN2, OUTPUT);
  pinMode(PIN_IN3, OUTPUT);
  pinMode(PIN_IN4, OUTPUT);
  stopMotors();

  // Allow allocation of all timers for servos
  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);

  // Attach servos (standard 50Hz, 500-2400µs pulse range)
  servoLE.setPeriodHertz(50);
  servoLW.setPeriodHertz(50);
  servoRE.setPeriodHertz(50);
  servoRW.setPeriodHertz(50);

  servoLE.attach(PIN_L_ELBOW, 500, 2400);
  servoLW.attach(PIN_L_WRIST, 500, 2400);
  servoRE.attach(PIN_R_ELBOW, 500, 2400);
  servoRW.attach(PIN_R_WRIST, 500, 2400);

  // Move to home
  armsHome();

  Serial.println("READY");
}

// ═════════════════════════════════════════════════════════════════
void loop() {
  // 1. Read serial commands
  while (Serial.available() > 0) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      serialBuffer.trim();
      if (serialBuffer.length() > 0) {
        processCommand(serialBuffer);
        serialBuffer = "";
      }
    } else {
      serialBuffer += c;
    }
  }

  // 2. Smooth servo movement (interpolate towards targets)
  smoothMove();

  // 3. Read ultrasonic distance
  lastDistance = readUltrasonic();

  // 4. Safety override — stop motors if obstacle too close
  if (lastDistance < OBSTACLE_DISTANCE_CM) {
    if (!obstacleActive) {
      obstacleActive = true;
      stopMotors();
      Serial.print("OBSTACLE:");
      Serial.println(lastDistance);
    }
  } else {
    if (obstacleActive) {
      obstacleActive = false;
      // Resume previous state
      if (baseState == 'C') {
        moveCircle();
      }
    }
    // Apply base state (only if no obstacle)
    if (baseState == 'S') {
      stopMotors();
    } else if (baseState == 'C') {
      moveCircle();
    }
  }

  delay(20);  // ~50Hz loop
}

// ═════════════════════════════════════════════════════════════════
//  COMMAND PARSER
// ═════════════════════════════════════════════════════════════════
void processCommand(String cmd) {

  // Single-character commands
  if (cmd == "C" || cmd == "c") {
    baseState = 'C';
    if (!obstacleActive) moveCircle();
    Serial.println("OK");
    return;
  }

  if (cmd == "S" || cmd == "s") {
    baseState = 'S';
    stopMotors();
    Serial.println("OK");
    return;
  }

  if (cmd == "H" || cmd == "h") {
    targetLE = HOME_LE;
    targetLW = HOME_LW;
    targetRE = HOME_RE;
    targetRW = HOME_RW;
    sendAngles("OK");
    return;
  }

  if (cmd == "?") {
    // Full status query
    String status = "STATUS:";
    status += baseState;
    status += ":LE:" + String((int)currentLE);
    status += ":LW:" + String((int)currentLW);
    status += ":RE:" + String((int)currentRE);
    status += ":RW:" + String((int)currentRW);
    status += ":D:"  + String(lastDistance);
    Serial.println(status);
    return;
  }

  // Arm command: A:LE:110:LW:20:RE:90:RW:40
  if (cmd.startsWith("A:")) {
    parseArmCommand(cmd);
    return;
  }

  Serial.println("ERR:UNKNOWN");
}

// ═════════════════════════════════════════════════════════════════
//  ARM COMMAND PARSER
//  Format: A:LE:110:LW:20:RE:90:RW:40
//  Can send partial updates too: A:LE:110  or  A:LE:110:RW:50
// ═════════════════════════════════════════════════════════════════
void parseArmCommand(String cmd) {
  // Remove "A:" prefix
  String data = cmd.substring(2);

  // Parse key:value pairs
  while (data.length() > 0) {
    int colonIdx = data.indexOf(':');
    if (colonIdx == -1) break;

    String key = data.substring(0, colonIdx);
    data = data.substring(colonIdx + 1);

    int nextColon = data.indexOf(':');
    String valStr;
    if (nextColon == -1) {
      valStr = data;
      data = "";
    } else {
      valStr = data.substring(0, nextColon);
      data = data.substring(nextColon + 1);
    }

    int val = valStr.toInt();
    val = constrain(val, 0, 180);

    if (key == "LE")      targetLE = val;
    else if (key == "LW") targetLW = val;
    else if (key == "RE") targetRE = val;
    else if (key == "RW") targetRW = val;
  }

  sendAngles("OK");
}

// ═════════════════════════════════════════════════════════════════
//  SMOOTH SERVO MOVEMENT
//  Interpolates current angles toward target at ~5° per tick
// ═════════════════════════════════════════════════════════════════
void smoothMove() {
  currentLE = interpolate(currentLE, targetLE, 5.0);
  currentLW = interpolate(currentLW, targetLW, 5.0);
  currentRE = interpolate(currentRE, targetRE, 5.0);
  currentRW = interpolate(currentRW, targetRW, 5.0);

  servoLE.write((int)currentLE);
  servoLW.write((int)currentLW);
  servoRE.write((int)currentRE);
  servoRW.write((int)currentRW);
}

float interpolate(float current, float target, float maxStep) {
  float diff = target - current;
  if (abs(diff) < 0.5) return target;
  float step = diff * 0.3;  // Ease-in factor
  if (step > maxStep)  step = maxStep;
  if (step < -maxStep) step = -maxStep;
  return current + step;
}

// ═════════════════════════════════════════════════════════════════
//  MOTOR FUNCTIONS
// ═════════════════════════════════════════════════════════════════
void stopMotors() {
  digitalWrite(PIN_IN1, LOW);
  digitalWrite(PIN_IN2, LOW);
  digitalWrite(PIN_IN3, LOW);
  digitalWrite(PIN_IN4, LOW);
}

void moveCircle() {
  // Left motor forward, right motor backward = spin in circle
  // Swap HIGH/LOW if motors spin wrong direction
  digitalWrite(PIN_IN1, HIGH);
  digitalWrite(PIN_IN2, LOW);
  digitalWrite(PIN_IN3, LOW);
  digitalWrite(PIN_IN4, HIGH);
}

// ═════════════════════════════════════════════════════════════════
//  ULTRASONIC SENSOR
// ═════════════════════════════════════════════════════════════════
long readUltrasonic() {
  digitalWrite(PIN_TRIG, LOW);
  delayMicroseconds(2);
  digitalWrite(PIN_TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(PIN_TRIG, LOW);

  long duration = pulseIn(PIN_ECHO, HIGH, 30000);
  if (duration == 0) return 999;
  return duration * 0.034 / 2;
}

// ═════════════════════════════════════════════════════════════════
//  HELPER: Send current angles
// ═════════════════════════════════════════════════════════════════
void sendAngles(String prefix) {
  String msg = prefix;
  msg += ":LE:" + String(targetLE);
  msg += ":LW:" + String(targetLW);
  msg += ":RE:" + String(targetRE);
  msg += ":RW:" + String(targetRW);
  Serial.println(msg);
}

void armsHome() {
  targetLE = HOME_LE;
  targetLW = HOME_LW;
  targetRE = HOME_RE;
  targetRW = HOME_RW;
  // Instantly jump to home on boot
  currentLE = HOME_LE;
  currentLW = HOME_LW;
  currentRE = HOME_RE;
  currentRW = HOME_RW;
  servoLE.write(HOME_LE);
  servoLW.write(HOME_LW);
  servoRE.write(HOME_RE);
  servoRW.write(HOME_RW);
}
