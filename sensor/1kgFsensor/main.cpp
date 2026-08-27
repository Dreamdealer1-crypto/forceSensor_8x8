/*
 * HX711 Load Cell Test — ATMega2560
 * 接线: DT → D3, SCK → D2
 * 打开串口监视器 115200 查看输出
 */

#include "HX711.h"

#define DT_PIN  14
#define SCK_PIN 15

HX711 scale;

void setup() {
  Serial.begin(115200);
  while (!Serial) {}

  Serial.println("=== HX711 Load Cell Test ===");
  Serial.println("Initializing...");

  scale.begin(DT_PIN, SCK_PIN);

  // 等待 HX711 就绪
  while (!scale.is_ready()) {
    Serial.println("Waiting for HX711...");
    delay(200);
  }

  // 读取零载原始值（空载时运行，不要放东西）
  Serial.println("Taring... DO NOT touch the sensor!");
  delay(2000);
  scale.tare(20);  // 取 20 次平均作为零点

  Serial.print("Zero offset: ");
  Serial.println(scale.get_offset());
  Serial.println();
  Serial.println("Tare done. You can now apply force.");
  Serial.println("Format: raw_reading, tared_reading");
  Serial.println("------------------------------------");
}

void loop() {
  if (scale.is_ready()) {
    long raw = scale.read();
    long tared = raw - scale.get_offset();

    Serial.print(raw);
    Serial.print(", ");
    Serial.println(tared);
  }
  delay(100);  // ~10 Hz 输出
}
