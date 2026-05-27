#pragma once
//
// Hardware Abstraction Layer.
//
// Three interfaces (Display, InputSource, Board) hide the board-specific
// panel + input controller behind a single API. main.cpp and views.cpp
// only see this header; the backends under hal/<board>/ link in
// per-PlatformIO-env via build_src_filter.

#include <Arduino.h>
#include <stdint.h>

namespace hal {

// 5-6-5 packed RGB. Both backends render at 16 bpp.
using Color = uint16_t;

constexpr Color COLOR_BLACK    = 0x0000;
constexpr Color COLOR_WHITE    = 0xFFFF;
constexpr Color COLOR_RED      = 0xF800;
constexpr Color COLOR_GREEN    = 0x07E0;
constexpr Color COLOR_BLUE     = 0x001F;
constexpr Color COLOR_YELLOW   = 0xFFE0;
constexpr Color COLOR_CYAN     = 0x07FF;
constexpr Color COLOR_MAGENTA  = 0xF81F;
constexpr Color COLOR_ORANGE   = 0xFD20;
constexpr Color COLOR_DARKGREY = 0x7BEF;

// Font selection. Backends map to whatever their native font system provides;
// the contract is glyph dimensions, not the underlying font file.
//   Ascii    — backend default ASCII font. Glyph cell is `6 * scale` wide.
//   CjkMixed — handles CJK + ASCII; glyph cell is `11 * scale` wide (square).
//              Only intended for short labels (counter subtitle).
enum class FontFamily : uint8_t { Ascii, CjkMixed };

struct TextStyle {
  Color      color  = COLOR_WHITE;
  FontFamily family = FontFamily::Ascii;
  uint8_t    scale  = 2;  // 1 = footer/IP, 2 = body, 3 = headline
};

class Display {
 public:
  virtual ~Display() = default;

  virtual int width() const = 0;
  virtual int height() const = 0;

  virtual void clear(Color bg = COLOR_BLACK) = 0;
  virtual void fillRect(int x, int y, int w, int h, Color c) = 0;

  // (x, y) is the top-left of the text bounding box. UTF-8 input.
  virtual void drawText(int x, int y, const char* text, const TextStyle& style) = 0;

  // Pixel width for layout. UTF-8 aware: continuation bytes don't count.
  virtual int  measureText(const char* text, FontFamily family, uint8_t scale) const = 0;

  // Push canvas to the panel. Backends that double-buffer commit here.
  virtual void flush() = 0;
};

// Semantic input events. Bound by the app to actions like "cycle view"
// or "toggle feeding"; the binding stays the same across boards. The
// backend decides what raw hardware event maps to each (DNESP32S3B:
// K1 / K2; ESP32-P4-7B: two touch regions).
using ActionCallback = void(*)();

class InputSource {
 public:
  virtual ~InputSource() = default;

  virtual void onPrimaryAction(ActionCallback cb) = 0;    // cycle view
  virtual void onSecondaryAction(ActionCallback cb) = 0;  // toggle feeding

  // Called from loop(); reads hardware state and fires callbacks.
  virtual void poll() = 0;
};

class Board {
 public:
  virtual ~Board() = default;

  // One-shot bring-up. Returns false if a required peripheral failed;
  // the app should still proceed (display may render with backlight off,
  // etc.) — the goal is "no hard crash on partial hardware."
  virtual bool init() = 0;

  virtual Display&     display() = 0;
  virtual InputSource& input() = 0;

  // 0..255 perceived brightness. Backends that only support on/off
  // (DNESP32S3B XL9555 P0.7) treat >=128 as on.
  virtual void backlight(uint8_t level) = 0;
};

// Provided by the per-board factory under hal/<board>/board.cpp. Exactly
// one backend's board.cpp is compiled per PlatformIO env.
Board& currentBoard();

}  // namespace hal
