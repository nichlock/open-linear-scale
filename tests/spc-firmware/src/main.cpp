#include <Arduino.h>

const int REQ_PIN = D2;
const int CLK_PIN = D3;
const int DATA_PIN = D4;
const uint32_t TIMEOUT_MS = 200;

enum ReadResult { READ_OK, READ_TIMEOUT, READ_INVALID };

ReadResult readGauge(float &value) {
  uint8_t digits[13] = {0};
  uint32_t start = millis();

  digitalWrite(REQ_PIN, LOW);
  for (int i = 0; i < 13; i++) {
    for (int j = 0; j < 4; j++) {
      while (digitalRead(CLK_PIN) == HIGH) {
        if (millis() - start > TIMEOUT_MS) {
          digitalWrite(REQ_PIN, HIGH);
          return READ_TIMEOUT;
        }
      }
      digitalWrite(REQ_PIN, HIGH);
      digits[i] |= digitalRead(DATA_PIN) << j;
      while (digitalRead(CLK_PIN) == LOW) {
        if (millis() - start > TIMEOUT_MS) {
          return READ_TIMEOUT;
        }
      }
    }
  }

  for (int i = 0; i < 4; i++) {
    if (digits[i] != 0xF) {
      return READ_INVALID;
    }
  }

  long raw = 0;
  for (int i = 5; i <= 10; i++) {
    raw = raw * 10 + digits[i];
  }
  value = raw / pow(10, digits[11]);
  if (digits[4] == 8) {
    value = -value;
  }
  return READ_OK;
}

void setup() {
  Serial.begin(115200);
  pinMode(REQ_PIN, OUTPUT_OPEN_DRAIN);
  digitalWrite(REQ_PIN, HIGH);
  pinMode(CLK_PIN, INPUT_PULLUP);
  pinMode(DATA_PIN, INPUT_PULLUP);
}

void loop() {
  float value;
  switch (readGauge(value)) {
    case READ_OK:
      Serial.println(value, 4);
      break;
    case READ_TIMEOUT:
      Serial.println("FAULT: no connection (timeout)");
      break;
    case READ_INVALID:
      Serial.println("FAULT: invalid data");
      break;
  }
  delay(10);
}
