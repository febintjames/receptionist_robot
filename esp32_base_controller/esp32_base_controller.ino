// ESP32 Base Controller for Receptionist Robot
// Receives Serial commands from Raspberry Pi:
// 'C' = Circle (move in circle)
// 'S' = Stop
// Hardware safety override: If ultrasonic distance < 100cm, STOP immediately.

// Ultrasonic Sensor Pins
#define TRIG_PIN 12
#define ECHO_PIN 14

// L298N Motor Driver Pins
#define IN1 25
#define IN2 26
#define IN3 27
#define IN4 33

// Robot State
char currentState = 'S'; // 'S' for Stop, 'C' for Circle

void setup() {
  Serial.begin(115200);

  // Initialize Ultrasonic Pins
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  // Initialize Motor Pins
  pinMode(IN1, OUTPUT);
  pinMode(IN2, OUTPUT);
  pinMode(IN3, OUTPUT);
  pinMode(IN4, OUTPUT);

  stopMotors();
  Serial.println("ESP32 Base Controller Ready.");
}

void loop() {
  // 1. Check Serial for new commands from Raspberry Pi
  if (Serial.available() > 0) {
    char cmd = Serial.read();
    if (cmd == 'C' || cmd == 'c') {
      currentState = 'C';
    } else if (cmd == 'S' || cmd == 's') {
      currentState = 'S';
    }
  }

  // 2. Read Ultrasonic Distance
  long duration, distance_cm;
  
  // Send 10us pulse
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  
  // Read echo
  duration = pulseIn(ECHO_PIN, HIGH, 30000); // 30ms timeout (~5 meters)
  
  if (duration == 0) {
    distance_cm = 999; // No echo received (clear path)
  } else {
    distance_cm = duration * 0.034 / 2;
  }

  // 3. Hardware Safety Override
  // If an obstacle is closer than 100cm, force a stop regardless of Pi's command
  if (distance_cm < 100) {
    stopMotors();
    Serial.print("OBSTACLE DETECTED! DIstance: ");
    Serial.print(distance_cm);
    Serial.println("cm. Forcing STOP.");
    delay(50); // Small delay before polling again
    return;
  }

  // 4. Apply State
  if (currentState == 'S') {
    stopMotors();
  } else if (currentState == 'C') {
    moveCircle();
  }

  // Loop delay to prevent spamming the ultrasonic sensor
  delay(50);
}

// ---- Motor Control Functions ----

void stopMotors() {
  digitalWrite(IN1, LOW);
  digitalWrite(IN2, LOW);
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, LOW);
}

void moveCircle() {
  // To move in a circle, spin left motor forward and right motor backward
  // (Adjust IN pins if your motors spin the wrong way)
  digitalWrite(IN1, HIGH);
  digitalWrite(IN2, LOW);
  
  digitalWrite(IN3, LOW);
  digitalWrite(IN4, HIGH);
}
