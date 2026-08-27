#include <Arduino.h>

#define DT_PIN 30
#define SCK_PIN 31

void setup() {
  Serial.begin(115200);
  while (!Serial) {}

  pinMode(DT_PIN, INPUT_PULLUP);
  pinMode(SCK_PIN, OUTPUT);
  digitalWrite(SCK_PIN, LOW);

  Serial.println("=== D30 Line Test ===");
  Serial.println("D30 uses INPUT_PULLUP. It should read 1 normally, 0 when D30 is connected to GND.");
  Serial.println("Keep HX711 SCK/CLK on D31 if connected. Test DT/DOUT wire by touching D30 to GND.");
}

void loop() {
  Serial.print("D30=");
  Serial.print(digitalRead(DT_PIN));
  Serial.print(", D31=");
  Serial.println(digitalRead(SCK_PIN));
  delay(200);
}
