#include "display.h"
#include <Arduino.h>

namespace hal::esp32p4_7b {

bool DisplayMipiDsi::init() {
  Serial.println("[hal-esp32p4-7b] display stub — MIPI-DSI bring-up pending");
  Serial.println("[hal-esp32p4-7b] see ARCHITECTURE/firmware-hal.md Open Gaps");
  return true;
}

void DisplayMipiDsi::clear(Color)                              {}
void DisplayMipiDsi::fillRect(int, int, int, int, Color)       {}
void DisplayMipiDsi::drawText(int, int, const char*, const TextStyle&) {}
void DisplayMipiDsi::flush()                                   {}

// UTF-8 aware char count × per-font glyph cell, same as DNESP32S3B.
// Phase B will revisit if the chosen font renderer (likely LVGL) reports
// glyph widths directly.
int DisplayMipiDsi::measureText(const char* text, FontFamily family, uint8_t scale) const {
  if (!text) return 0;
  int chars = 0;
  for (const char* p = text; *p; ++p) {
    if (((uint8_t)*p & 0xC0) != 0x80) chars++;
  }
  int glyphW = (family == FontFamily::CjkMixed) ? 11 : 6;
  return chars * glyphW * scale;
}

}  // namespace hal::esp32p4_7b
