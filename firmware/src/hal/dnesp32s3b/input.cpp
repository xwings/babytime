#include "input.h"
#include <Wire.h>

namespace hal::dnesp32s3b {

namespace {
constexpr uint8_t XL9555_ADDR    = 0x20;
constexpr uint8_t XL9555_INPUT0  = 0x00;
constexpr uint8_t XL_KEY1_PIN    = 4;  // P0.4
constexpr uint8_t XL_KEY2_PIN    = 3;  // P0.3

constexpr uint32_t POLL_MS           = 60;
constexpr uint32_t DEBOUNCE_MS       = 80;
constexpr uint32_t K1_LONG_PRESS_MS  = 1500;

bool readPort(uint8_t reg, uint8_t& val) {
  Wire.beginTransmission(XL9555_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((int)XL9555_ADDR, 1) != 1) return false;
  val = Wire.read();
  return true;
}
}  // namespace

bool InputXl9555::init() {
  // Board::init() configures the expander + backlight; we just mark ready.
  // A wrong-on-the-bus device would still satisfy this — first poll() will
  // fail silently and no callbacks fire.
  ready_ = true;
  return true;
}

void InputXl9555::poll() {
  if (!ready_) return;
  if (millis() - lastPollMs_ < POLL_MS) return;
  lastPollMs_ = millis();

  uint8_t p0 = 0xFF;
  if (!readPort(XL9555_INPUT0, p0)) return;
  bool k1Pressed = ((p0 >> XL_KEY1_PIN) & 0x01) == 0;
  bool k2Pressed = ((p0 >> XL_KEY2_PIN) & 0x01) == 0;

  handleShortOrLong(k1_, k1Pressed, primary_, sync_, K1_LONG_PRESS_MS);
  handleRelease(k2_, k2Pressed, secondary_);
}

void InputXl9555::handleShortOrLong(ButtonState& b, bool pressed,
                                    ActionCallback shortCb, ActionCallback longCb,
                                    uint32_t longMs) {
  uint32_t nowMs = millis();
  if (pressed != b.pressed) {
    if (nowMs - b.lastChangeMs <= DEBOUNCE_MS) return;
    b.lastChangeMs = nowMs;
    b.pressed = pressed;
    if (pressed) {
      b.pressStartMs = nowMs;
      b.longFired = false;
    } else if (!b.longFired && shortCb) {
      shortCb();
    }
    return;
  }
  if (pressed && !b.longFired && (nowMs - b.pressStartMs >= longMs)) {
    b.longFired = true;
    if (longCb) longCb();
  }
}

void InputXl9555::handleRelease(ButtonState& b, bool pressed, ActionCallback releaseCb) {
  uint32_t nowMs = millis();
  if (pressed == b.pressed) return;
  if (nowMs - b.lastChangeMs <= DEBOUNCE_MS) return;
  b.lastChangeMs = nowMs;
  b.pressed = pressed;
  if (!pressed && releaseCb) releaseCb();
}

}  // namespace hal::dnesp32s3b
