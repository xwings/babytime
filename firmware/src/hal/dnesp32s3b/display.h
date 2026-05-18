#pragma once
#include "hal/hal.h"

class Arduino_DataBus;
class Arduino_GFX;
class Arduino_Canvas;

namespace hal::dnesp32s3b {

// ST7789V 240x320 via LCD_CAM 8-bit parallel (Arduino_ESP32LCD8).
// Double-buffered: writes go to an Arduino_Canvas, flush() commits.
class DisplayLcdCam : public Display {
 public:
  DisplayLcdCam();

  bool init();  // ordering: must run before Wire.begin() on this board.

  int  width()  const override;
  int  height() const override;
  void clear(Color bg) override;
  void fillRect(int x, int y, int w, int h, Color c) override;
  void drawText(int x, int y, const char* text, const TextStyle& style) override;
  int  measureText(const char* text, FontFamily family, uint8_t scale) const override;
  void flush() override;

 private:
  Arduino_DataBus* bus_;
  Arduino_GFX*     panel_;
  Arduino_Canvas*  canvas_;
};

}  // namespace hal::dnesp32s3b
