#include <Arduino.h>

struct Pair {
  const char *name;
  uint8_t dt;
  uint8_t sck;
};

Pair pairs[] = {
  {"DT=22 SCK=23", 22, 23},
  {"DT=23 SCK=22", 23, 22},
  {"DT=30 SCK=31", 30, 31},
  {"DT=31 SCK=30", 31, 30},
  {"DT=2 SCK=3", 2, 3},
  {"DT=3 SCK=2", 3, 2},
};

bool waitReady(uint8_t dt, uint16_t timeoutMs) {
  unsigned long start = millis();
  while (digitalRead(dt) == HIGH && millis() - start < timeoutMs) {
    delay(1);
  }
  return digitalRead(dt) == LOW;
}

long readHx711(uint8_t dt, uint8_t sck) {
  long value = 0;
  for (int i = 0; i < 24; i++) {
    digitalWrite(sck, HIGH);
    delayMicroseconds(1);
    value = (value << 1) | digitalRead(dt);
    digitalWrite(sck, LOW);
    delayMicroseconds(1);
  }

  digitalWrite(sck, HIGH);
  delayMicroseconds(1);
  digitalWrite(sck, LOW);

  if (value & 0x800000) {
    value |= 0xFF000000;
  }
  return value;
}

void setup() {
  Serial.begin(115200);
  while (!Serial) {}

  for (Pair &pair : pairs) {
    pinMode(pair.dt, INPUT_PULLUP);
    pinMode(pair.sck, OUTPUT);
    digitalWrite(pair.sck, LOW);
  }

  Serial.println("=== HX711 Multi Pin Probe ===");
}

void loop() {
  for (Pair &pair : pairs) {
    pinMode(pair.dt, INPUT_PULLUP);
    pinMode(pair.sck, OUTPUT);
    digitalWrite(pair.sck, LOW);
    delay(100);

    Serial.print(pair.name);
    Serial.print(" -> ");

    if (!waitReady(pair.dt, 500)) {
      Serial.println("not ready");
      continue;
    }

    Serial.print("READ=");
    Serial.println(readHx711(pair.dt, pair.sck));
  }

  Serial.println("---");
  delay(1000);
}
