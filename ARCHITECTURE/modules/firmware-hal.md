---
eatmycode_version: "2.0.0"
---
# Firmware Hardware Abstraction

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `firmware/src/hal/`, `firmware/platformio.ini`, `firmware/partitions.csv`, `Makefile`, board selection, pins, display or raw input.

## Responsibility and Status

Owns hardware interfaces, board backends and firmware build selection.
DNESP32S3B driver is implemented but hardware checks are **in progress**.
ESP32-P4-7B is **scaffolding**: display methods are no-ops, touch callbacks
never fire and backlight is ignored. Both environments compile locally;
that does not establish P4 hardware support. Legacy Phase B names the
pending display/touch/network bring-up, not a completed milestone.

## Code Map

| Path / symbol | Role |
| --- | --- |
| `firmware/src/hal/hal.h`: `Display`, `InputSource`, `Board`, `currentBoard` | RGB565 display/font/action contracts and factory. |
| `firmware/src/hal/dnesp32s3b/{board,display,input}.{h,cpp}` | LCD_CAM/ST7789V, canvas, XL9555 and button-release behavior; board has only `.cpp`. |
| `firmware/src/hal/esp32p4_7b/{board,display,input}.{h,cpp}` | P4 stub backend; board has only `.cpp`. |
| `firmware/platformio.ini`, `firmware/partitions.csv`, `Makefile` | Per-board source filters, dependencies, memory map and build wrappers. |

## Local Conventions

Follow [root style](../../ARCHITECTURE.md#code-conventions). C++ uses nested
namespaces and virtual interfaces; the repository has no explicit `-std`
override or formatter. Each backend exports exactly one `currentBoard()`
factory; source filtering selects it, not runtime board detection. Keep
hardware register/pin details local; app views must not include driver APIs.

## Contracts and Invariants

- `Display` exposes dimensions, clear/fill, text measurement/drawing and
  explicit `flush`. RGB565 colors and UTF-8 lead-byte glyph counting are
  shared conventions; ASCII cell width is `6*scale`, CJK `11*scale`.
- `InputSource` provides only Primary and Secondary callbacks plus `poll`.
  There is no sync action or K1 long-press callback despite stale app
  comments/constants. Backends map hardware to semantic actions.
- DNESP32S3B is ESP32-S3 with configured 16 MB flash and OPI PSRAM.
  `DisplayLcdCam` uses Arduino_GFX ST7789 with a 320×240 landscape canvas.
  **Initialize LCD before `Wire.begin()`**: the board source documents a
  hang if I²C precedes LCD_CAM. Board initialization then enables backlight
  and input. A failed backlight write logs and continues; app ignores the
  board init return value.
- DN pins: I²C SDA=48/SCL=45, XL9555 address `0x20`, K1=P0.4,
  K2=P0.3, backlight=P0.7. `display.cpp` is canonical for the parallel LCD
  pin set. K2/BOOT hardware strapping is distinct from expander polling.
  Input polls every 60 ms and debounces changes for 80 ms; actions fire on
  release. Failed I²C reads silently skip that poll.
- Backlight accepts 0–255; DN maps >=128 to on. Stub P4 ignores it. P4
  dimensions are nominal 1024×600, never evidence that pixels were shown.
- PlatformIO envs exclude the other board's HAL source subtree. Shared
  ArduinoJson is `^7.4.2`; DN adds GFX Library `^1.6.0` and U8g2 `^2.36.5`.
  P4 currently has no panel/touch dependency. pioarduino's moving `stable`
  archive and caret library ranges are not reproducible version pins.
- `Makefile` defaults to DN, 115200 monitor baud and `pio` on PATH;
  `DEVICE`, `PIO`, `PORT`, `BAUD` are supported overrides. The DN partition
  file contains two 3 MB app slots and the remaining SPIFFS region; a
  partition layout does not imply implemented OTA or filesystem behavior.

## Dependencies and Boundaries

[Application](firmware-app.md) binds actions and composes all views; read it
when changing dimensions/fonts/callback semantics. HAL has no gateway
route dependency. Driver libraries come only from PlatformIO configuration;
`.pio` contains generated/downloaded artifacts and is not edited source.
A private base config is an application build prerequisite, not a driver.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| --- | --- | --- |
| Board / build selection | Env filter, factory, board flags | Both root builds; exactly one factory in each linked target. |
| DN panel / pins / input | Backend + init ordering | Real-board LCD/backlight/button verification and app views. |
| P4 implementation | Stub display/input/board and manifests | Panel/touch/C6 networking on physical hardware; preserve semantic actions. |
| Fonts / dimensions | Display contract and measurement | App owner; CJK and long labels, bounds and explicit flush. |

## Verification

Run both firmware build commands from root Verification. Both passed locally
with existing local config. Pass means compile/link/resource reporting,
not panel/touch/network behavior. If `pio` is off PATH use the Makefile's
`PIO` override; first build needs network/toolchain downloads.

For connected hardware, `make monitor DEVICE=dnesp32s3b` should observe
`LCD init...` before backlight/network logs; K1 cycles views and K2 logs a
feeding End after release. Real P4 verification remains pending: current
stub logs plus a blank panel/no touch are expected, not a successful
hardware implementation. No flashing or hardware checks ran in this refresh.

## Known Gaps

Phase B remains pending: EK79007 MIPI-DSI display, GT911 touch, backlight
PWM and ESP32-C6/SDIO `esp_hosted` Wi-Fi verification. The older design
mentions shared touch/LCD I²C SDA=7/SCL=8, but these pins are not implemented
or validated here; use board schematics before coding. A custom Arduino
variant and ESP32_Display_Panel are proposals, not installed dependencies.
A larger touch-oriented view is deferred until hardware works. No runtime
font metrics, HAL unit tests or board fixtures exist. Compiler/library
pinning and the missing tracked base config limit fresh-clone evidence.
