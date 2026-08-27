#include <Arduino.h>

#define DT_PIN  22
#define SCK_PIN 23

void setup() {
  Serial.begin(115200);
  while (!Serial) {}

  pinMode(DT_PIN, INPUT_PULLUP);
  pinMode(SCK_PIN, OUTPUT);
  digitalWrite(SCK_PIN, LOW);

  Serial.println("=== HX711 Probe ===");
  Serial.println("Expected: DOUT/DT -> D22, SCK/CLK -> D23");
}

void loop() {
  unsigned long start = millis();
  while (digitalRead(DT_PIN) == HIGH && millis() - start < 1000) {
    delay(1);
  }

  if (digitalRead(DT_PIN) == HIGH) {
    Serial.println("DOUT stayed HIGH for 1000 ms");
    return;
  }

  long value = 0;
  for (int i = 0; i < 24; i++) {
    digitalWrite(SCK_PIN, HIGH);
    delayMicroseconds(1);
    value = (value << 1) | digitalRead(DT_PIN);
    digitalWrite(SCK_PIN, LOW);
    delayMicroseconds(1);
  }

  digitalWrite(SCK_PIN, HIGH);
  delayMicroseconds(1);
  digitalWrite(SCK_PIN, LOW);

  if (value & 0x800000) {
    value |= 0xFF000000;
  }

  Serial.print("READ=");
  Serial.println(value);
  delay(100);
}
