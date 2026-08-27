#include <Arduino.h>

static const uint8_t CMD_READ_A = 0xA1;
static const uint8_t FRAME_START = 0xAA;
static const uint8_t FRAME_END = 0xFF;

static bool readFrame(uint8_t frame[10], unsigned long timeoutMs) {
  unsigned long start = millis();

  while (millis() - start < timeoutMs) {
    if (!Serial3.available()) {
      continue;
    }

    uint8_t b = Serial3.read();
    if (b != FRAME_START) {
      continue;
    }

    frame[0] = b;
    for (int i = 1; i < 10; i++) {
      unsigned long byteStart = millis();
      while (!Serial3.available() && millis() - byteStart < 10) {}
      if (!Serial3.available()) {
        return false;
      }
      frame[i] = Serial3.read();
    }
    return true;
  }
  return false;
}

static bool checksumOk(const uint8_t frame[10]) {
  if (frame[0] != FRAME_START || frame[9] != FRAME_END) {
    return false;
  }

  uint16_t sum = 0;
  for (int i = 1; i <= 6; i++) {
    sum += frame[i];
  }
  uint16_t got = ((uint16_t)frame[7] << 8) | frame[8];
  return sum == got;
}

static uint32_t parseRaw(const uint8_t frame[10]) {
  return ((uint32_t)frame[4] << 16) | ((uint32_t)frame[5] << 8) | frame[6];
}

void setup() {
  Serial.begin(115200);
  while (!Serial) {}

  Serial3.begin(9600);
  Serial.println("raw,delta");
}

void loop() {
  static unsigned long lastQuery = 0;
  if (millis() - lastQuery < 50) {
    return;
  }
  lastQuery = millis();

  while (Serial3.available()) {
    Serial3.read();
  }

  uint8_t command[10] = {
    FRAME_START,
    CMD_READ_A,
    0x00,
    0x00,
    0x00,
    0x00,
    0x00,
    0x00,
    CMD_READ_A,
    FRAME_END,
  };
  Serial3.write(command, sizeof(command));

  uint8_t frame[10];
  if (!readFrame(frame, 80) || !checksumOk(frame)) {
    return;
  }

  uint32_t raw = parseRaw(frame);
  static bool hasBaseline = false;
  static int32_t baseline = 0;
  if (!hasBaseline) {
    baseline = (int32_t)raw;
    hasBaseline = true;
  }

  Serial.print(raw);
  Serial.print(",");
  Serial.println((int32_t)raw - baseline);
}
