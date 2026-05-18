#pragma once
#include "hal/hal.h"

namespace hal::esp32p4_7b {

// Stub: Waveshare ESP32-P4-WIFI6-Touch-LCD-7B uses an EK79007 1024×600
// MIPI-DSI panel. Phase B wires this up via ESP32_Display_Panel; today
// every primitive is a no-op and the dimensions are panel-truth so layout
// math in views.cpp produces a self-consistent (if invisible) frame.
class DisplayMipiDsi : public Display {
 public:
  bool init();

  int  width()  const override { return 1024; }
  int  height() const override { return 600; }

  void clear(Color bg) override;
  void fillRect(int x, int y, int w, int h, Color c) override;
  void drawText(int x, int y, const char* text, const TextStyle& style) override;
  int  measureText(const char* text, FontFamily family, uint8_t scale) const override;
  void flush() override;
};

}  // namespace hal::esp32p4_7b
