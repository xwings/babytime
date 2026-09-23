---
eatmycode_version: "2.1.0"
---
# Firmware Hardware Abstraction

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `firmware/src/hal/`, `firmware/platformio.ini`, `firmware/partitions.csv`, `Makefile`, board selection, pins, display or raw input.

## Responsibility and Status

Owns hardware interfaces, board backends and firmware build selection.
DNESP32S3B driver is implemented; hardware checks are **in progress**.
ESP32-P4-7B is **scaffolding**: display methods are no-ops, touch callbacks
never fire and backlight is ignored, yet its `init()` returns true. No
build ran in this refresh (PlatformIO absent); compiling the stub would not
establish P4 support. "Phase B" in source comments names the pending P4
display/touch/network bring-up.

## Code Map

| Path / symbol | Role |
| --- | --- |
| `firmware/src/hal/hal.h`: `Display`, `InputSource`, `Board`, `TextStyle`, `currentBoard` | RGB565 display/font/action contracts and the factory declaration. |
| `firmware/src/hal/dnesp32s3b/`: `DisplayLcdCam`, `InputXl9555`, `board.cpp` | LCD_CAM/ST7789 canvas, XL9555 buttons/backlight, init ordering; board has only `.cpp`. |
| `firmware/src/hal/esp32p4_7b/`: `DisplayMipiDsi`, `InputTouch`, `board.cpp` | P4 stub backend that prints this doc's path at boot. |
| `firmware/platformio.ini`, `firmware/partitions.csv`, `Makefile` | Per-board source filters, flags, dependencies, DN memory map and build wrappers. |

## Local Conventions

Follow [root style](../../ARCHITECTURE.md#code-conventions). C++ uses nested
namespaces (`hal::dnesp32s3b`, `hal::esp32p4_7b`) and virtual interfaces;
no explicit `-std` override or formatter exists. Each backend exports
exactly one `currentBoard()` factory from an anonymous-namespace board
class; `build_src_filter` selects it, not runtime detection. Keep register
and pin details local; app views must not include driver APIs.

## Contracts and Invariants

- `hal.h`: `Color = uint16_t` with named RGB565 constants; `FontFamily
  {Ascii, CjkMixed}`; `TextStyle{color, family, scale=2}`; `ActionCallback`.
  `Display` pure virtuals: `width`, `height`, `clear(bg)`, `fillRect`,
  `drawText(x, y, text, style)`, `measureText(text, family, scale)`,
  `flush`. `InputSource`: `onPrimaryAction`, `onSecondaryAction`, `poll`.
  `Board`: `init() -> bool`, `display()`, `input()`, `backlight(uint8_t)`.
  Backend `init()` methods are extras outside the interface.
- Text measurement counts UTF-8 lead bytes: ASCII cell `6*scale`, CJK
  `11*scale`. `hal.h` documents `(x, y)` as top-left, but the DN backend
  uses `setCursor`+`print` and the u8g2 CJK font positions at baseline, so
  views offset CJK subtitles by 16 px. Font changes must keep that offset
  consistent.
- No sync action or K1 long-press callback exists despite stale app
  comments; backends map hardware to the two semantic actions only.
- DNESP32S3B: ESP32-S3, 16 MB flash, OPI PSRAM (`board_build.*` in the DN
  env). `DisplayLcdCam` drives Arduino_GFX ST7789 over `Arduino_ESP32LCD8`
  (DC=2, CS=1, WR=42, RD=41, D0–D7=40,39,38,12,11,10,9,46) into a 320×240
  landscape canvas with `u8g2_font_cubic11_h_cjk`. **Initialize LCD before
  `Wire.begin()`** (100 kHz): the board source documents a hang otherwise.
  `Board::init` returns only the LCD result; a failed backlight write logs
  and continues; the app ignores the return value.
- DN pins: I²C SDA=48/SCL=45, XL9555 at `0x20` (INPUT0 `0x00`, OUTPUT0
  `0x02`, CONFIG0 `0x06`), K1=P0.4, K2=P0.3, backlight=P0.7 as the only
  output bit. Buttons are active-low; `README.md` says "K2/BOOT GPIO 0" but
  the firmware never reads GPIO 0. Input polls every 60 ms, rejects edges
  within 80 ms of the last accepted edge, fires actions on release and
  skips a poll on I²C read failure.
- Backlight accepts 0–255; DN maps >=128 to on and init already enables it.
  Stub P4 ignores it, reports nominal 1024×600 and measures text for real.
- `platformio.ini`: envs `dnesp32s3b` (`esp32-s3-devkitc-1`) and `esp32p4_7b`
  (`esp32-p4`); shared flags `ARDUINO_USB_CDC_ON_BOOT=1`, `ARDUINO_USB_MODE=1`,
  `BOARD_HAS_PSRAM`, `CORE_DEBUG_LEVEL=2`, `-Isrc`; DN adds `U8G2_*` font
  flags. `BOARD_DNESP32S3B`/`BOARD_ESP32P4_7B` are defined but unreferenced.
  `partitions.csv` (two 3 MB app slots, otadata, ~9.9 MB SPIFFS) applies to
  DN only; P4 uses the board default. Shared ArduinoJson `^7.4.2`; DN adds
  GFX Library `^1.6.0` and U8g2 `^2.36.5`; P4 has no panel/touch library.
  The pioarduino `stable` archive and caret ranges are not pins.
- `Makefile` targets: `help`, `build`, `flash`, `monitor`, `flash-monitor`,
  `clean`; variables `DEVICE` (default dnesp32s3b), `PIO`, `PORT`, `BAUD`
  (115200). `flash-monitor` omits monitor flags, so `PORT`/`BAUD` apply only
  to its upload leg. A partition layout does not imply OTA or filesystem code.

## Dependencies and Boundaries

[Application](firmware-app.md) binds actions and composes all views; read
it when changing dimensions, fonts or callback semantics. HAL has no
gateway dependency. Driver libraries come only from PlatformIO
configuration; `.pio` holds generated artifacts. The private base config
is an application build prerequisite, not a driver concern.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| --- | --- | --- |
| Board / build selection | Env filter, factory, board flags | Both root builds; exactly one factory in each linked target. |
| DN panel / pins / input | Backend + init ordering | Real-board LCD/backlight/button verification and app views. |
| P4 implementation | Stub display/input/board and manifests | Panel/touch/C6 networking on physical hardware; preserve semantic actions. |
| Fonts / dimensions | Display contract, measurement, baseline offset | App owner; CJK and long labels, bounds and explicit flush. |

## Verification

Run both firmware build commands from root Verification. Pass means
compile/link/resource reporting, not panel/touch/network behavior. If
`pio` is off PATH use the Makefile `PIO` override; the first build needs
network for toolchain downloads. No build ran in this refresh.

Connected DN hardware: `make monitor DEVICE=dnesp32s3b` should show
`LCD init...` before backlight/network logs; K1 cycles views and K2 logs a
feeding End on release. On P4 the stub prints and a blank panel are the
expected state, not evidence of support. No HAL unit tests exist.

## Known Gaps

Phase B remains pending: EK79007 MIPI-DSI display, GT911 touch, backlight
PWM and ESP32-C6/SDIO `esp_hosted` Wi-Fi. Shared touch/LCD I²C SDA=7/SCL=8
from the older design is not implemented or validated; use board schematics
before coding. A custom Arduino variant and ESP32_Display_Panel are
proposals, not dependencies. A touch-oriented view is deferred until
hardware works. No runtime font metrics, HAL unit tests or board fixtures
exist. Unpinned compiler/library versions and the missing tracked base
config limit fresh-clone evidence.
