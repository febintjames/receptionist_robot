// ============================================================
// ESP32 Receptionist Robot Controller
// Handles 4 servos, 2 DC motors (L298N), and HC-SR04 Ultrasonic
// Serial Protocol:
//   C              -> Base: circle
//   S              -> Base: stop
//   A:LE:xx:LW:xx:RE:xx:RW:xx -> Set arm angles
//   H              -> Arms: home
//   ?              -> Query status
// ============================================================

#include "BluetoothSerial.h"
#include <ESP32Servo.h>

BluetoothSerial BT;
Servo leftElbow, leftWrist, rightElbow, rightWrist;

// ── Pins ─────────────────────────────────────────────────────
#define LEFT_ELBOW_PIN 21
#define LEFT_WRIST_PIN 19
#define RIGHT_ELBOW_PIN 23
#define RIGHT_WRIST_PIN 22

#define IN1_PIN 27
#define IN2_PIN 26
#define IN3_PIN 33
#define IN4_PIN 25

#define ENA_PIN 14 // PWM Enable pin for Left Motor (IN1/IN2)
#define ENB_PIN 32 // PWM Enable pin for Right Motor (IN3/IN4)

#define TRIG_PIN 5
#define ECHO_PIN 18

// ── Calibrated physical limits ───────────────────────────────
#define LE_MIN 30
#define LE_MAX 90
#define LW_MIN 10
#define LW_MAX 70
#define RE_MIN 70
#define RE_MAX 130
#define RW_MIN 10
#define RW_MAX 60

// ── Mid position (Home) ──────────────────────────────────────
#define LE_HOME 60
#define LW_HOME 40
#define RE_HOME 100
#define RW_HOME 30

float le_pos = LE_HOME, lw_pos = LW_HOME, re_pos = RE_HOME, rw_pos = RW_HOME;
float le_tgt = LE_HOME, lw_tgt = LW_HOME, re_tgt = RE_HOME, rw_tgt = RW_HOME;

// ── State ────────────────────────────────────────────────────
unsigned long lastUltraTime = 0;
int currentDistance = 999;
bool obstacleActive = false;
bool motorsMoving = false; // Add state

// ── Square Patrol State Machine ──────────────────────────────
enum SquareState {
  STOPPED,
  SQUARE_FORWARD,
  SQUARE_TURNING,
  OBSTACLE_WAIT,
  MANUAL_OVERRIDE
};
SquareState squareState = STOPPED;
SquareState stateBeforePause = STOPPED;
int squareSide = 0;
unsigned long stateStart = 0;
unsigned long timeElapsedBeforePause = 0;

int forwardMs[4] = {3000, 3000, 3000, 3000};
int turnMs[4] = {1200, 1200, 1200, 1200};
const int MOVE_SPEED = 110;

void setup() {
  Serial.begin(115200);
  BT.begin("RobotBase"); // Bluetooth device name

  ESP32PWM::allocateTimer(0);
  ESP32PWM::allocateTimer(1);
  ESP32PWM::allocateTimer(2);
  ESP32PWM::allocateTimer(3);

  leftElbow.setPeriodHertz(50);
  leftElbow.attach(LEFT_ELBOW_PIN, 500, 2500);
  leftWrist.setPeriodHertz(50);
  leftWrist.attach(LEFT_WRIST_PIN, 500, 2500);
  rightElbow.setPeriodHertz(50);
  rightElbow.attach(RIGHT_ELBOW_PIN, 500, 2500);
  rightWrist.setPeriodHertz(50);
  rightWrist.attach(RIGHT_WRIST_PIN, 500, 2500);

  pinMode(IN1_PIN, OUTPUT);
  pinMode(IN2_PIN, OUTPUT);
  pinMode(IN3_PIN, OUTPUT);
  pinMode(IN4_PIN, OUTPUT);

  pinMode(ENA_PIN, OUTPUT);
  pinMode(ENB_PIN, OUTPUT);

  stopMotors();

  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  writeAll();

  Serial.println("READY");
}

void loop() {
  // ── USB Serial ──
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    if (cmd.length() > 0) {
      handleCommand(cmd);
    }
  }

  // ── Bluetooth Serial ──
  if (BT.available() > 0) {
    String cmd = BT.readStringUntil('\n');
    cmd.trim();
    cmd.toUpperCase();
    if (cmd.length() > 0) {
      handleBTCommand(cmd);
    }
  }

  // Ultrasonic ~100ms
  unsigned long now = millis();
  if (now - lastUltraTime > 100) {
    lastUltraTime = now;
    checkUltrasonic();
  }

  runSquareStateMachine();

  smoothStep();
  delay(15);
}

void handleCommand(String cmd) {
  if (cmd == "C") {
    if (!obstacleActive) {
      squareSide = 0;
      stateStart = millis();
      squareState = SQUARE_FORWARD;
      driveForward();
      Serial.println("OK");
    } else {
      Serial.println("ERR:OBSTACLE_ACTIVE");
    }
  } else if (cmd == "S") {
    if (squareState != STOPPED && squareState != MANUAL_OVERRIDE && squareState != OBSTACLE_WAIT) {
      stateBeforePause = squareState;
      timeElapsedBeforePause = millis() - stateStart;
    }
    squareState = STOPPED;
    stopMotors();
    Serial.println("OK");
  } else if (cmd == "RESUME") {
    // Python backend confirmed obstacle is NOT a human — resume patrol from
    // where we paused
    obstacleActive = false;
    stateStart = millis() - timeElapsedBeforePause;
    squareState = stateBeforePause;
    if (squareState == SQUARE_FORWARD) {
      driveForward();
    } else if (squareState == SQUARE_TURNING) {
      pivotLeft();
    } else {
      // stateBeforePause was STOPPED or unknown — just start a fresh forward
      // leg
      squareSide = 0;
      squareState = SQUARE_FORWARD;
      driveForward();
    }
    Serial.println("OK");
  } else if (cmd == "H") {
    le_tgt = LE_HOME;
    lw_tgt = LW_HOME;
    re_tgt = RE_HOME;
    rw_tgt = RW_HOME;
    Serial.println("OK");
  } else if (cmd.startsWith("A:")) {
    // Better parse approach:
    int ptr = 2; // skip "A:"
    while (ptr < cmd.length()) {
      int nextColon = cmd.indexOf(':', ptr);
      if (nextColon == -1)
        break;
      String key = cmd.substring(ptr, nextColon);
      int valEnd = cmd.indexOf(':', nextColon + 1);
      if (valEnd == -1)
        valEnd = cmd.length();
      int val = cmd.substring(nextColon + 1, valEnd).toInt();
      if (key == "LE")
        le_tgt = val;
      else if (key == "LW")
        lw_tgt = val;
      else if (key == "RE")
        re_tgt = val;
      else if (key == "RW")
        rw_tgt = val;
      ptr = valEnd + 1;
    }
    Serial.println("OK");
  } else if (cmd == "?") {
    Serial.print("STATUS:");
    Serial.print(motorsMoving ? "C" : "S");
    Serial.print(":LE:");
    Serial.print((int)le_pos);
    Serial.print(":LW:");
    Serial.print((int)lw_pos);
    Serial.print(":RE:");
    Serial.print((int)re_pos);
    Serial.print(":RW:");
    Serial.print((int)rw_pos);
    Serial.print(":D:");
    Serial.println(currentDistance);
  }
}

void checkUltrasonic() {
  // Skip the ultrasonic entirely while already handling an obstacle
  // obstacleActive is only cleared by a RESUME or S command from Python.
  if (obstacleActive)
    return;

  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);

  long duration = pulseIn(ECHO_PIN, HIGH, 30000);
  if (duration == 0) {
    currentDistance = 999;
    return;
  }
  currentDistance = duration * 0.034 / 2;

  if (currentDistance < 50 && currentDistance > 0) {
    // First detection — lock obstacle state and stop motors
    obstacleActive = true;
    if (squareState != STOPPED && squareState != OBSTACLE_WAIT &&
        squareState != MANUAL_OVERRIDE) {
      stateBeforePause = squareState;
      timeElapsedBeforePause = millis() - stateStart;
      squareState = OBSTACLE_WAIT;
    }
    stopMotors();
    // Send ONE alert to Python — Python will decide human or inanimate
    Serial.print("OBSTACLE:");
    Serial.println(currentDistance);
  }
}

void handleBTCommand(String cmd) {
  if (cmd == "F" || cmd == "FORWARD") {
    enterManualMode();
    driveForward();
    BT.println("> Fwd");
  } else if (cmd == "B" || cmd == "BACKWARD") {
    enterManualMode();
    driveBackward();
    BT.println("> Back");
  } else if (cmd == "L" || cmd == "LEFT") {
    enterManualMode();
    pivotLeft();
    BT.println("> Left");
  } else if (cmd == "R" || cmd == "RIGHT") {
    enterManualMode();
    pivotRight();
    BT.println("> Right");
  } else if (cmd == "S" || cmd == "STOP") {
    squareState = STOPPED;
    stopMotors();
    BT.println("> Stop");
  } else if (cmd == "G" || cmd == "RESUME") {
    if (squareState == MANUAL_OVERRIDE || squareState == OBSTACLE_WAIT) {
      obstacleActive = false;
      stateStart = millis() - timeElapsedBeforePause;
      squareState = stateBeforePause;
      if (squareState == SQUARE_FORWARD)
        driveForward();
      else if (squareState == SQUARE_TURNING)
        pivotLeft(); // turn is always left
      else {
        squareSide = 0;
        squareState = SQUARE_FORWARD;
        driveForward();
      }
      BT.println("> Autopilot Resumed");
    } else {
      BT.println("> Cannot Resume from STOP");
    }
  }
}

void enterManualMode() {
  if (squareState != MANUAL_OVERRIDE) {
    if (squareState != STOPPED && squareState != OBSTACLE_WAIT) {
      stateBeforePause = squareState;
      timeElapsedBeforePause = millis() - stateStart;
    }
    squareState = MANUAL_OVERRIDE;
    stopMotors();
  }
}

void driveForward() {
  motorsMoving = true;
  digitalWrite(IN1_PIN, HIGH);
  digitalWrite(IN2_PIN, LOW);
  digitalWrite(IN3_PIN, HIGH);
  digitalWrite(IN4_PIN, LOW);
  analogWrite(ENA_PIN, MOVE_SPEED);
  analogWrite(ENB_PIN, MOVE_SPEED);
}

void driveBackward() {
  motorsMoving = true;
  digitalWrite(IN1_PIN, LOW);
  digitalWrite(IN2_PIN, HIGH);
  digitalWrite(IN3_PIN, LOW);
  digitalWrite(IN4_PIN, HIGH);
  analogWrite(ENA_PIN, MOVE_SPEED);
  analogWrite(ENB_PIN, MOVE_SPEED);
}

void pivotLeft() {
  motorsMoving = true;
  digitalWrite(IN1_PIN, LOW);
  digitalWrite(IN2_PIN, HIGH);
  digitalWrite(IN3_PIN, HIGH);
  digitalWrite(IN4_PIN, LOW);
  analogWrite(ENA_PIN, MOVE_SPEED);
  analogWrite(ENB_PIN, MOVE_SPEED);
}

void pivotRight() {
  motorsMoving = true;
  digitalWrite(IN1_PIN, HIGH);
  digitalWrite(IN2_PIN, LOW);
  digitalWrite(IN3_PIN, LOW);
  digitalWrite(IN4_PIN, HIGH);
  analogWrite(ENA_PIN, MOVE_SPEED);
  analogWrite(ENB_PIN, MOVE_SPEED);
}

void stopMotors() {
  motorsMoving = false;
  digitalWrite(IN1_PIN, LOW);
  digitalWrite(IN2_PIN, LOW);
  digitalWrite(IN3_PIN, LOW);
  digitalWrite(IN4_PIN, LOW);
  analogWrite(ENA_PIN, 0);
  analogWrite(ENB_PIN, 0);
}

void runSquareStateMachine() {
  unsigned long now = millis();
  switch (squareState) {
  case SQUARE_FORWARD:
    if (now - stateStart >= (unsigned long)forwardMs[squareSide]) {
      // Segment complete — go straight to turning left
      pivotLeft();
      squareState = SQUARE_TURNING;
      stateStart = now;
    }
    break;
  case SQUARE_TURNING:
    if (now - stateStart >= (unsigned long)turnMs[squareSide]) {
      squareSide = (squareSide + 1) % 4;
      driveForward();
      squareState = SQUARE_FORWARD;
      stateStart = now;
    }
    break;
  case OBSTACLE_WAIT:
  case STOPPED:
  case MANUAL_OVERRIDE:
    break;
  }
}

void smoothStep() {
  bool moved = false;
  auto step = [](float &cur, float tgt) -> bool {
    float diff = tgt - cur;
    if (abs(diff) < 0.5) {
      cur = tgt;
      return false;
    }
    float s = diff * 0.12;
    if (s > 3.0)
      s = 3.0;
    if (s < -3.0)
      s = -3.0;
    cur += s;
    return true;
  };

  moved |= step(le_pos, le_tgt);
  moved |= step(lw_pos, lw_tgt);
  moved |= step(re_pos, re_tgt);
  moved |= step(rw_pos, rw_tgt);

  if (moved)
    writeAll();
}

void writeAll() {
  leftElbow.write(constrain((int)le_pos, LE_MIN, LE_MAX));
  leftWrist.write(constrain((int)lw_pos, LW_MIN, LW_MAX));
  rightElbow.write(constrain((int)re_pos, RE_MIN, RE_MAX));
  rightWrist.write(constrain((int)rw_pos, RW_MIN, RW_MAX));
}
