#include <Arduino.h>

#define DT_PIN  22
#define SCK_PIN 23

void setup() {
  Serial.begin(115200);
  while (!Serial) {}

  pinMode(DT_PIN, INPUT_PULLUP);
  pinMode(SCK_PIN, OUTPUT);
  digitalWrite(SCK_PIN, LOW);

  Serial.println("=== HX711 Pin Diagnostic ===");
  Serial.println("Expected wiring: DOUT/DT -> D22, SCK/CLK -> D23");
  Serial.println("Format: dt_level, sck_level");
}

void loop() {
  int dt = digitalRead(DT_PIN);
  int sck = digitalRead(SCK_PIN);

  Serial.print("DT=");
  Serial.print(dt);
  Serial.print(", SCK=");
  Serial.println(sck);
  delay(200);
}
