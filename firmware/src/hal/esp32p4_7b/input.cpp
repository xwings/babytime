#include "input.h"
#include <Arduino.h>

namespace hal::esp32p4_7b {

bool InputTouch::init() {
  Serial.println("[hal-esp32p4-7b] touch stub — GT911 bring-up pending");
  return true;
}

}  // namespace hal::esp32p4_7b
