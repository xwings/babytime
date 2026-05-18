#include "display.h"
#include <Arduino_GFX_Library.h>

namespace hal::dnesp32s3b {

namespace {
// DNESP32S3B (Alientek) — ST7789V via parallel 8080 8-bit (LCD_CAM).
constexpr int8_t LCD_DC = 2, LCD_CS = 1, LCD_WR = 42, LCD_RD = 41;
constexpr int8_t LCD_D0 = 40, LCD_D1 = 39, LCD_D2 = 38, LCD_D3 = 12;
constexpr int8_t LCD_D4 = 11, LCD_D5 = 10, LCD_D6 = 9,  LCD_D7 = 46;

constexpr int PANEL_W = 320;
constexpr int PANEL_H = 240;

// 6 px per glyph for the default Arduino_GFX font, 11 px for cubic11 CJK.
constexpr int ASCII_GLYPH_W = 6;
constexpr int CJK_GLYPH_W   = 11;
}  // namespace

DisplayLcdCam::DisplayLcdCam()
    : bus_(new Arduino_ESP32LCD8(LCD_DC, LCD_CS, LCD_WR, LCD_RD,
                                 LCD_D0, LCD_D1, LCD_D2, LCD_D3,
                                 LCD_D4, LCD_D5, LCD_D6, LCD_D7)),
      panel_(new Arduino_ST7789(bus_, GFX_NOT_DEFINED, 1, true, 240, 320, 0, 0, 0, 0)),
      canvas_(new Arduino_Canvas(PANEL_W, PANEL_H, panel_, 0, 0, 0)) {}

bool DisplayLcdCam::init() {
  bool ok = canvas_->begin();
  canvas_->setUTF8Print(true);  // multi-byte decode for u8g2 CJK fonts
  canvas_->fillScreen(COLOR_BLACK);
  canvas_->flush();
  return ok;
}

int DisplayLcdCam::width()  const { return canvas_->width(); }
int DisplayLcdCam::height() const { return canvas_->height(); }

void DisplayLcdCam::clear(Color bg) { canvas_->fillScreen(bg); }

void DisplayLcdCam::fillRect(int x, int y, int w, int h, Color c) {
  canvas_->fillRect(x, y, w, h, c);
}

void DisplayLcdCam::drawText(int x, int y, const char* text, const TextStyle& s) {
  if (s.family == FontFamily::CjkMixed) {
    canvas_->setFont(u8g2_font_cubic11_h_cjk);
  } else {
    canvas_->setFont();
  }
  canvas_->setTextColor(s.color);
  canvas_->setTextSize(s.scale);
  canvas_->setCursor(x, y);
  canvas_->print(text);
}

int DisplayLcdCam::measureText(const char* text, FontFamily family, uint8_t scale) const {
  if (!text) return 0;
  int chars = 0;
  for (const char* p = text; *p; ++p) {
    if (((uint8_t)*p & 0xC0) != 0x80) chars++;  // count UTF-8 lead bytes
  }
  int glyphW = (family == FontFamily::CjkMixed) ? CJK_GLYPH_W : ASCII_GLYPH_W;
  return chars * glyphW * scale;
}

void DisplayLcdCam::flush() { canvas_->flush(); }

}  // namespace hal::dnesp32s3b
