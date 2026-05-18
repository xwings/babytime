# firmware-hal

## Goal

Single Hardware Abstraction Layer that hides the panel + input
controller behind three interfaces (`Display`, `InputSource`,
`Board`) so [firmware-app.md](firmware-app.md) builds once and runs
on either supported device. Phase A delivers the DNESP32S3B backend
(behavior-identical to the pre-HAL firmware) plus a compiling-but-
silent ESP32-P4-7B stub backend; Phase B brings the P4 panel and
touch up.

Infrastructure under every feature; no milestone gate.

## Status

`in progress (Phase B)`. Interfaces and DNESP32S3B backend are
`done` — `make build DEVICE=dnesp32s3b` passes and hardware behavior
is unchanged from before the refactor. ESP32-P4-7B backend is a
`scaffolding` stub: `make build DEVICE=esp32p4_7b` links cleanly,
but `init()` only logs a TODO, no pixels are pushed, and touch
events never fire. Phase B (real MIPI-DSI + GT911 + esp_hosted
Wi-Fi bring-up on hardware) is tracked in Open Gaps.

## Code Structure

| File | Role |
| ---- | ---- |
| `firmware/src/hal/hal.h` | Interfaces (`Display`, `InputSource`, `Board`), `Color` (RGB565), `FontFamily`, `TextStyle`, color constants, `currentBoard()` factory |
| `firmware/src/hal/dnesp32s3b/display.h` | `DisplayLcdCam` interface declaration |
| `firmware/src/hal/dnesp32s3b/display.cpp` | ST7789V via `Arduino_ESP32LCD8` + `Arduino_ST7789` + `Arduino_Canvas`; ASCII default font + u8g2 cubic11 CJK |
| `firmware/src/hal/dnesp32s3b/input.h` | `InputXl9555` interface + button-state FSM |
| `firmware/src/hal/dnesp32s3b/input.cpp` | XL9555 (I²C `0x20`) polling, debounce, K1-short/long FSM |
| `firmware/src/hal/dnesp32s3b/board.cpp` | LCD-before-Wire bring-up, backlight via XL9555 P0.7, factory binding |
| `firmware/src/hal/esp32p4_7b/display.h` | `DisplayMipiDsi` stub interface (1024×600 dimensions are panel-truth) |
| `firmware/src/hal/esp32p4_7b/display.cpp` | All paint primitives are no-ops; `measureText` returns plausible widths so views.cpp layout math doesn't divide by zero |
| `firmware/src/hal/esp32p4_7b/input.h` | `InputTouch` stub — callbacks stored, never fired |
| `firmware/src/hal/esp32p4_7b/input.cpp` | (empty body; touch wire-up deferred) |
| `firmware/src/hal/esp32p4_7b/board.cpp` | Stub `init()` logs TODO; factory binding |

`build_src_filter` in `firmware/platformio.ini` excludes the other
board's `hal/<board>/` subtree from each env, so exactly one
`currentBoard()` symbol is linked per binary — no `#ifdef` forest in
the bodies.

## Key Types and Entry Points

- `firmware/src/hal/hal.h:16` — `using Color = uint16_t` (RGB565).
- `firmware/src/hal/hal.h:18-27` — Named color constants (BLACK,
  WHITE, RED, GREEN, BLUE, YELLOW, CYAN, MAGENTA, ORANGE, DARKGREY).
- `firmware/src/hal/hal.h:34` — `enum class FontFamily { Ascii,
  CjkMixed }`. Contract is glyph cell width (6 px / 11 px), not the
  underlying font file.
- `firmware/src/hal/hal.h:36-40` — `struct TextStyle { Color color;
  FontFamily family; uint8_t scale; }`.
- `firmware/src/hal/hal.h:42-60` — `class Display` —
  `width/height/clear/fillRect/drawText/measureText/flush`.
- `firmware/src/hal/hal.h:66` — `using ActionCallback = void(*)()`.
- `firmware/src/hal/hal.h:68-78` — `class InputSource` —
  `onPrimaryAction` (cycle view), `onSecondaryAction` (toggle
  feeding), `onSyncRequest` (manual sync), `poll()`.
- `firmware/src/hal/hal.h:80-95` — `class Board` —
  `init/display/input/backlight`.
- `firmware/src/hal/hal.h:99` — `Board& currentBoard()` — provided
  by exactly one backend per env.
- `firmware/src/hal/dnesp32s3b/board.cpp:33-53` —
  `DnEsp32S3bBoard::init` — LCD-before-Wire ordering, XL9555
  backlight, then input.
- `firmware/src/hal/dnesp32s3b/display.cpp:20-25` — `DisplayLcdCam`
  ctor — LCD_CAM 8-bit parallel pin set + ST7789 + canvas.
- `firmware/src/hal/dnesp32s3b/display.cpp:44-54` —
  `DisplayLcdCam::drawText` — font switch (default ASCII /
  u8g2_font_cubic11_h_cjk).
- `firmware/src/hal/dnesp32s3b/input.cpp:26-32` — `InputXl9555::init`
  — assumes Board already brought up Wire + XL9555.
- `firmware/src/hal/dnesp32s3b/input.cpp:34-46` — `InputXl9555::poll`
  — reads XL9555 input port 0, dispatches K1/K2 FSM.
- `firmware/src/hal/dnesp32s3b/input.cpp:48-68` —
  `InputXl9555::handleShortOrLong` — K1 short on release if
  long-fire didn't claim it; long fires at `K1_LONG_PRESS_MS = 1500`.
- `firmware/src/hal/dnesp32s3b/input.cpp:70-77` —
  `InputXl9555::handleRelease` — K2 fires on release after debounce.
- `firmware/src/hal/esp32p4_7b/board.cpp:11-16` —
  `Esp32P4_7BBoard::init` — stub log, then display + input stubs.

## Interactions

- Implements the surface consumed by
  [firmware-app.md](firmware-app.md): `main.cpp` calls
  `hal::currentBoard().init()` and binds input callbacks; `views.cpp`
  derives layout from `display().width()/height()` and paints via the
  `Display` primitives.
- No dependency on [gateway-api.md](gateway-api.md) — the HAL is
  hardware-only.
- DNESP32S3B backend depends on `Arduino_GFX_Library` +
  `U8g2` (declared in `firmware/platformio.ini` `[env:dnesp32s3b]`).
  ESP32-P4-7B backend has no extra deps in Phase A; Phase B will
  add `esp-arduino-libs/ESP32_Display_Panel`.

## How to Test

- `make build DEVICE=dnesp32s3b` — pass = PlatformIO reports
  `SUCCESS` with the dnesp32s3b RAM/Flash usage table.
- `make build DEVICE=esp32p4_7b` — pass = PlatformIO reports
  `SUCCESS` with the esp32p4_7b RAM/Flash usage table (first run
  pulls the RISC-V toolchain, ~5–10 min).
- `make flash-monitor DEVICE=dnesp32s3b` — pass = serial prints `LCD
  init...`, then `Backlight ON`, then Wi-Fi/NTP lines; K1 short
  cycles view, K1 long (≥1.5 s) shows sync banner, K2 toggles
  feeding.
- `make flash-monitor DEVICE=esp32p4_7b` (if hardware available) —
  pass = serial prints `[hal-esp32p4-7b] display stub — MIPI-DSI
  bring-up pending` and the app then idles. Screen stays blank; no
  crash. Touch is dead by design in Phase A.

## Open Gaps / Roadmap

- **Phase B — ESP32-P4-7B panel bring-up.** Replace
  `hal/esp32p4_7b/display.cpp` no-ops with an `ESP32_Display_Panel`-
  backed implementation for the EK79007 MIPI-DSI 1024×600 panel.
  Add `esp-arduino-libs/ESP32_Display_Panel` to
  `firmware/platformio.ini` `[env:esp32p4_7b]` `lib_deps`.
- **Phase B — GT911 touch.** Replace `hal/esp32p4_7b/input.cpp`
  no-op `poll()` with GT911 I²C polling (shared bus with the LCD
  path: SCL=GPIO8, SDA=GPIO7). Map three on-screen regions to
  primary/secondary/sync callbacks — keep the semantic split so app
  code is unchanged.
- **Phase B — Wi-Fi via esp_hosted.** The 7B board's Wi-Fi 6 comes
  from an onboard ESP32-C6 over SDIO. Verify the slave firmware is
  pre-flashed (Waveshare ships it that way); confirm `WiFi.h`
  associates without changes to `connectWiFi()` in
  `firmware/src/main.cpp`.
- **Phase B — custom Arduino variant.** May need
  `firmware/include/variants/esp32p4_7b/pins_arduino.h` for
  esp_hosted SDIO pin defines once the Waveshare schematic is read.
- **Phase B — touch-redesigned dashboard.** The big counter +
  on-screen Start/Stop + scrollable history layout the user asked
  for needs new `views.cpp` paths gated on
  `display().width() >= 1024`, or a parallel `views_touch.cpp`.
  Decision deferred until hardware in hand.
- **Backlight PWM.** `Board::backlight(uint8_t)` interface is 0..255
  but DNESP32S3B XL9555 P0.7 is on/off only (≥128 treated as on);
  ESP32-P4-7B stub ignores the level entirely. Phase B can wire
  real PWM on the DSI backlight pin.
- **Stub display dimensions.** `DisplayMipiDsi::width/height` return
  `1024/600` so layout math doesn't divide by zero — but the
  Phase A binary doesn't actually drive the panel, so the numbers
  are aspirational. Replace with runtime-discovered values once
  `ESP32_Display_Panel` is wired.
- **Product question (logged here for visibility, not firmware
  work).** Should the gateway UI surface `device_id` differently
  for the two board types (badge, icon)? Deferred until both
  devices are deployed.
