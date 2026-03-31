// ============================================================
// ESP32 Servo Controller — Receptionist Robot Arms
// Boot: arms go to MID position (natural rest)
// Movement: only happens during START_TALK
// Serial commands: START_TALK | STOP_GESTURE | SET:LW:45 | GET
// ============================================================

#include <ESP32Servo.h>

Servo leftElbow, leftWrist, rightElbow, rightWrist;

// ── Pins ─────────────────────────────────────────────────────
#define LEFT_ELBOW_PIN 21
#define LEFT_WRIST_PIN 19
#define RIGHT_ELBOW_PIN 23
#define RIGHT_WRIST_PIN 22

// ── Calibrated physical limits ───────────────────────────────
//  L_ELBOW: 90=down, 30=raised  (inverted servo)
//  L_WRIST: 10=down, 70=up
//  R_ELBOW: 70=down, 130=raised
//  R_WRIST: 10=down, 60=up
#define LE_MIN 30
#define LE_MAX 90
#define LW_MIN 10
#define LW_MAX 70
#define RE_MIN 70
#define RE_MAX 130
#define RW_MIN 10
#define RW_MAX 60

// ── Mid position (boot/idle resting pose) ───────────────────
// Calculated as midpoint of each servo's range
#define LE_MID 80 // mid of 30~90
#define LW_MID 70 // mid of 10~70
#define RE_MID 85 // mid of 70~130
#define RW_MID 20 // mid of 10~60  (slightly raised looks natural)

// ── Current positions ────────────────────────────────────────
float le_pos = LE_MID;
float lw_pos = LW_MID;
float re_pos = RE_MID;
float rw_pos = RW_MID;

// ── Target positions ─────────────────────────────────────────
float le_target = LE_MID;
float lw_target = LW_MID;
float re_target = RE_MID;
float rw_target = RW_MID;

// ── State ────────────────────────────────────────────────────
bool isTalking = false;
int talkPhase = 0;
unsigned long lastTalkMove = 0;

// ============================================================
void setup() {
  Serial.begin(115200);

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

  // Boot directly to mid position — no sweeping on power-on
  writeAll();

  Serial.println("Ready. Arms at mid position.");
  Serial.println("Commands: START_TALK | STOP_GESTURE | SET:LE:50 | GET");
}

// ============================================================
void loop() {
  // Read serial commands
  if (Serial.available() > 0) {
    String cmd = Serial.readStringUntil('\n');
    cmd.trim();
    handleCommand(cmd);
  }

  // Only animate when talking
  if (isTalking) {
    runTalkGesture();
  }

  // Smooth interpolation toward targets (always runs)
  smoothStep();

  delay(15);
}

// ============================================================
// Command Handler
// ============================================================
void handleCommand(String cmd) {

  if (cmd == "START_TALK") {
    isTalking = true;
    talkPhase = 0;
    lastTalkMove = 0;
    Serial.println("ACK: START_TALK");
  } else if (cmd == "STOP_GESTURE") {
    isTalking = false;
    // Return to mid position
    le_target = LE_MID;
    lw_target = LW_MID;
    re_target = RE_MID;
    rw_target = RW_MID;
    Serial.println("ACK: STOP_GESTURE — returning to mid");
  } else if (cmd == "HOME") {
    isTalking = false;
    le_target = LE_MID;
    lw_target = LW_MID;
    re_target = RE_MID;
    rw_target = RW_MID;
    Serial.println("ACK: HOME (mid position)");
  }
  // SET:JOINT:ANGLE — live angle test
  else if (cmd.startsWith("SET:")) {
    int firstColon = cmd.indexOf(':', 4);
    if (firstColon != -1) {
      String joint = cmd.substring(4, firstColon);
      int angle = constrain(cmd.substring(firstColon + 1).toInt(), 0, 180);
      if (joint == "LE") {
        le_target = angle;
        Serial.print("SET LE -> ");
        Serial.println(angle);
      } else if (joint == "LW") {
        lw_target = angle;
        Serial.print("SET LW -> ");
        Serial.println(angle);
      } else if (joint == "RE") {
        re_target = angle;
        Serial.print("SET RE -> ");
        Serial.println(angle);
      } else if (joint == "RW") {
        rw_target = angle;
        Serial.print("SET RW -> ");
        Serial.println(angle);
      } else {
        Serial.println("ERR: Use LE / LW / RE / RW");
      }
    }
  } else if (cmd == "GET") {
    Serial.print("LE:");
    Serial.print((int)le_pos);
    Serial.print(" LW:");
    Serial.print((int)lw_pos);
    Serial.print(" RE:");
    Serial.print((int)re_pos);
    Serial.print(" RW:");
    Serial.println((int)rw_pos);
  } else {
    Serial.println("ERR: Unknown command");
  }
}

// ============================================================
// Talk Gesture — sets new targets every 400~700ms
//
// Angle reference:
//   LE: 90=mid/down  30=raised   (inverted)
//   LW: 40=mid       10=down  70=up
//   RE: 100=mid      70=down  130=raised
//   RW: 30=mid       10=down  60=up
// ============================================================
void runTalkGesture() {
  unsigned long now = millis();
  if (now - lastTalkMove < (unsigned long)random(400, 700))
    return;
  lastTalkMove = now;

  switch (talkPhase % 4) {

  case 0:
    // Left arm lifts, right stays mid
    le_target = random(35, 55);  // LE raised from mid (60→35)
    lw_target = random(45, 65);  // LW up
    re_target = random(90, 110); // RE near mid
    rw_target = RW_MID;          // RW mid (30)
    break;

  case 1:
    // Right arm lifts, left returns mid
    re_target = random(110, 128); // RE raised from mid (100→128)
    rw_target = random(35, 55);   // RW up
    le_target = random(55, 70);   // LE near mid
    lw_target = LW_MID;           // LW mid (40)
    break;

  case 2:
    // Both wrists raise — open expressive gesture
    lw_target = random(50, 68);  // LW up
    rw_target = random(38, 55);  // RW up
    le_target = random(45, 60);  // LE mid-raised
    re_target = random(95, 115); // RE mid-raised
    break;

  case 3:
    // Gentle settle back near mid — subtle life
    le_target = random(55, 68);  // LE near mid (60)
    lw_target = random(32, 48);  // LW near mid (40)
    re_target = random(92, 108); // RE near mid (100)
    rw_target = random(22, 38);  // RW near mid (30)
    break;
  }

  talkPhase++;
}

// ============================================================
// Smooth step — interpolates current toward target each loop
// ============================================================
void smoothStep() {
  bool moved = false;

  auto step = [](float &cur, float tgt) -> bool {
    float diff = tgt - cur;
    if (abs(diff) < 0.5) {
      cur = tgt;
      return false;
    }
    float s = diff * 0.12;
    if (s > 2.5)
      s = 2.5;
    if (s < -2.5)
      s = -2.5;
    cur += s;
    return true;
  };

  moved |= step(le_pos, le_target);
  moved |= step(lw_pos, lw_target);
  moved |= step(re_pos, re_target);
  moved |= step(rw_pos, rw_target);

  if (moved)
    writeAll();
}

// ============================================================
// Write current positions to servos
// ============================================================
void writeAll() {
  leftElbow.write(constrain((int)le_pos, LE_MIN, LE_MAX));
  leftWrist.write(constrain((int)lw_pos, LW_MIN, LW_MAX));
  rightElbow.write(constrain((int)re_pos, RE_MIN, RE_MAX));
  rightWrist.write(constrain((int)rw_pos, RW_MIN, RW_MAX));
}