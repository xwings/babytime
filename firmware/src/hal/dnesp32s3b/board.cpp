#include "hal/hal.h"
#include "display.h"
#include "input.h"

#include <Arduino.h>
#include <Wire.h>

namespace {

constexpr uint8_t I2C_SDA           = 48;
constexpr uint8_t I2C_SCL           = 45;
constexpr uint8_t XL9555_ADDR       = 0x20;
constexpr uint8_t XL9555_OUTPUT0    = 0x02;
constexpr uint8_t XL9555_CONFIG0    = 0x06;
constexpr uint8_t XL_BACKLIGHT_PIN  = 7;  // P0.7

bool xl9555WriteReg(uint8_t reg, uint8_t val) {
  Wire.beginTransmission(XL9555_ADDR);
  Wire.write(reg);
  Wire.write(val);
  return Wire.endTransmission() == 0;
}

bool setBacklight(bool on) {
  uint8_t mask = (1 << XL_BACKLIGHT_PIN);
  uint8_t out  = on ? mask : 0;
  if (!xl9555WriteReg(XL9555_OUTPUT0, out)) return false;
  return xl9555WriteReg(XL9555_CONFIG0, ~mask & 0xFF);
}

class DnEsp32S3bBoard : public hal::Board {
 public:
  bool init() override {
    // Hardware quirk: LCD_CAM peripheral MUST initialize before I²C is
    // brought up on this board, or the chip hangs on Wire.begin().
    Serial.println("LCD init...");
    bool lcdOk = display_.init();
    if (!lcdOk) Serial.println("display init failed");

    Wire.setPins(I2C_SDA, I2C_SCL);
    Wire.begin();
    Wire.setClock(100000);

    if (setBacklight(true)) {
      backlightOn_ = true;
      Serial.println("Backlight ON");
    } else {
      Serial.println("XL9555 not responding; backlight stays off");
    }

    input_.init();
    return lcdOk;
  }

  hal::Display&     display() override { return display_; }
  hal::InputSource& input()   override { return input_; }

  void backlight(uint8_t level) override {
    bool want = level >= 128;
    if (want == backlightOn_) return;
    if (setBacklight(want)) backlightOn_ = want;
  }

 private:
  hal::dnesp32s3b::DisplayLcdCam display_;
  hal::dnesp32s3b::InputXl9555   input_;
  bool                           backlightOn_ = false;
};

DnEsp32S3bBoard g_board;

}  // namespace

namespace hal { Board& currentBoard() { return g_board; } }
