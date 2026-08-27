#include <Arduino.h>

#define DT_PIN A0
#define SCK_PIN A1

void setup() {
  Serial.begin(115200);
  while (!Serial) {}

  pinMode(DT_PIN, INPUT_PULLUP);
  pinMode(SCK_PIN, OUTPUT);
  digitalWrite(SCK_PIN, LOW);

  Serial.println("=== A0/A1 Line Test ===");
  Serial.println("A0 is DT/DOUT input. A1 is SCK/CLK output LOW.");
  Serial.println("Format: A0_DT, A1_SCK");
}

void loop() {
  Serial.print("A0_DT=");
  Serial.print(digitalRead(DT_PIN));
  Serial.print(", A1_SCK=");
  Serial.println(digitalRead(SCK_PIN));
  delay(200);
}
