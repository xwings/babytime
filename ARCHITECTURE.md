# feedingtime-esp32s3

This file is the control center. It carries only cross-cutting
material: mission, target environment, workspace layout, boot/entry
flow, hardware quirks, the pin map, the coding discipline this
project is written and reviewed against, and an index of
`ARCHITECTURE/<module>.md` files for each subsystem.

Per-subsystem prose lives in `ARCHITECTURE/`. Each module file
follows the template in the
[eatmycode skill](../../.claude/skills/eatmycode/SKILL.md) — section
headers are fixed (verification is grep-based).

## Mission

A baby-feeding tracker firmware that runs on one of two ESP32 boards
today. The device tracks one feeding session at a time (start / stop
with a button or touch), shows a live clock + last-fed counter +
recent history on its LCD, and runs untethered.

An optional Docker gateway turns the device into a multi-room
deployment: durable SQLite log, a web UI for editing records,
multiple devices sharing one source of truth, and outbound forwarding
to an OpenClaw agent (the "automation" backend) on demand or on a
schedule.

## Target environment

**Devices** (one binary per board, selected at build time via
`make DEVICE=<env>` — see [firmware-hal.md](ARCHITECTURE/firmware-hal.md)).

- **Alientek DNESP32S3B** (`DEVICE=dnesp32s3b`, default) —
  ESP32-S3R8, dual Xtensa LX7 @ 240 MHz, 16 MB flash, 8 MB OPI PSRAM.
  ST7789V 320×240 LCD driven via the LCD_CAM parallel-8080-8-bit
  peripheral. XL9555 (PCA9555-compatible) I/O expander at I²C `0x20`
  for K1/K2 buttons and LCD backlight. USB-CDC for flashing and
  serial. Wi-Fi 2.4 GHz on-chip.
- **Waveshare ESP32-P4-WIFI6-Touch-LCD-7B** (`DEVICE=esp32p4_7b`,
  Phase B for full hardware support) — ESP32-P4 RISC-V SoC with
  EK79007 1024×600 MIPI-DSI panel, GT911 capacitive touch (no
  physical buttons), Wi-Fi 6 via an onboard ESP32-C6 over SDIO
  (`esp_hosted`). Phase A ships a compiling stub backend; Phase B
  brings up the panel, touch, and Wi-Fi.

**Toolchain.** PlatformIO + pioarduino (Arduino framework on top of
ESP-IDF). Two envs in `firmware/platformio.ini` (`[env:dnesp32s3b]`
+ `[env:esp32p4_7b]`); per-env `build_src_filter` excludes the
other board's HAL backend so each binary links exactly one
`hal::currentBoard()`. Build/flash via `make` wrappers — pass
`DEVICE=<env>` to switch (see `Makefile`).

**Gateway.** Python 3 + FastAPI + SQLite, shipped as a Docker image
(`gateway/Dockerfile`, `gateway/docker-compose.yml`). Runs anywhere
that can run Docker; in practice a small Linux host on the same LAN
as the device(s).

## Workspace layout

```
firmware/        ESP32 firmware (PlatformIO project, two envs)
  src/main.cpp     board-agnostic app: state, gateway HTTP, NTP, setup/loop
  src/state.h      shared types + extern globals + time helpers
  src/views.h      view function declarations
  src/views.cpp    panel-size-aware view renderers (against hal::Display)
  src/hal/         Hardware Abstraction Layer (see firmware-hal.md)
    hal.h          Display / InputSource / Board interfaces
    dnesp32s3b/    ST7789V + XL9555 backend (compiled when DEVICE=dnesp32s3b)
    esp32p4_7b/    MIPI-DSI + GT911 stub backend (compiled when DEVICE=esp32p4_7b)
  include/         build-time config (config.h + config.local.h)
  lib/             empty (cleared when audio was removed)
  platformio.ini   shared [env] + [env:dnesp32s3b] + [env:esp32p4_7b]
gateway/         FastAPI + SQLite gateway, packaged as Docker
  app/             Python source (main, db, config, openclaw, util)
  app/templates/   server-rendered Jinja2 HTML
  app/static/      CSS
  Dockerfile, docker-compose.yml, requirements.txt
ARCHITECTURE/    per-subsystem design files (this directory's index)
Makefile         build / flash / monitor wrappers around pio (DEVICE=<env>)
README.md        user-facing setup notes
```

## Boot / entry flow

**Firmware** (`firmware/src/main.cpp`):

1. `setup()` calls `hal::currentBoard().init()` — the board-specific
   bring-up (e.g. the DNESP32S3B "LCD before Wire" quirk lives
   inside `hal/dnesp32s3b/board.cpp`; the ESP32-P4-7B backend has
   its own ordering). The semantic input callbacks (`cycleView`,
   `toggleFeeding`, `manualSync`) are then bound on
   `board.input()`, and Wi-Fi + NTP come up.
2. In gateway mode, `xTaskCreatePinnedToCore(gatewayTask, …, 0)`
   pins the HTTP client to Core 0.
3. `loop()` (Core 1) calls `board.input().poll()`, ticks the UI, and
   redraws when `gatewayStateDirty` is set by the Core 0 task.

**Gateway** (`gateway/Dockerfile`):

1. `docker compose up` → `uvicorn app.main:app --host 0.0.0.0 --port 8080`.
2. FastAPI's `lifespan` hook calls `db.init()`, runs the legacy
   config migration, and spawns `openclaw.scheduler_loop` as a
   background task.

## Hardware quirks

**DNESP32S3B — LCD before Wire.** LCD_CAM and I²C do not initialise
cleanly in parallel on this board: `gfx->begin()` (LCD_CAM
peripheral) must run **before** `Wire.begin()`, otherwise the chip
hangs. Encapsulated inside `firmware/src/hal/dnesp32s3b/board.cpp`
— no longer a project-wide rule, but documented here because anyone
touching that backend will hit it.

**ESP32-P4-7B — Wi-Fi over a second chip.** Wi-Fi 6 on this board
comes from an onboard ESP32-C6 over SDIO (`esp_hosted`). The C6 must
be running the pre-flashed Espressif slave firmware before
`WiFi.h` will associate; we treat that firmware as fixed and don't
ship it. Phase B verifies this on hardware.

## Pin map

### DNESP32S3B

| Pin source | Function |
| ---------- | -------- |
| GPIO 0 | K2 / BOOT (toggle feeding; also USB-DFU strap) |
| GPIO 45 | I²C SCL (XL9555) |
| GPIO 48 | I²C SDA (XL9555) |
| XL9555 P0.3 | K2 (toggle feeding, read via expander) |
| XL9555 P0.4 | K1 (cycle views; long-press = sync) |
| XL9555 P0.7 | LCD backlight enable |
| LCD_CAM 8-bit parallel | ST7789V data (driven by Arduino_GFX ESP32S3PAR8 bus) |

USB-CDC handles flashing and serial monitor; holding K2 during reset
puts the chip in download mode.

### ESP32-P4-WIFI6-Touch-LCD-7B (Phase B)

| Pin source | Function |
| ---------- | -------- |
| MIPI-DSI | EK79007 1024×600 panel (driven by ESP32_Display_Panel) |
| GPIO 7 / 8 | I²C SDA / SCL — shared by LCD config and GT911 touch |
| SDIO to onboard ESP32-C6 | Wi-Fi 6 via `esp_hosted` (pins per Waveshare schematic, TBD) |
| DSI backlight pin | PWM-capable (Phase B) |

No physical buttons on this board — three on-screen touch regions
map to the same primary / secondary / sync semantic actions.

## Coding Discipline

This project's code is written and reviewed against the following
eight principles. The standards applied when reviewing are the same
standards followed when writing.

1. **Module Depth.** Substantial functionality behind a simple
   interface. Maximize the gap between interface complexity and
   implementation complexity. Avoid trivial wrappers, one-use methods,
   and shallow classes. Prefer general-purpose interfaces; keep the
   common case simple.

2. **Information Hiding.** Encapsulate design decisions (data
   structures, algorithms, assumptions) inside one module. `private`
   alone is not hiding — getters/setters that expose internals still
   leak. Watch for back-door leakage (multiple modules knowing the
   same format) and temporal decomposition (one class per execution
   phase when the same knowledge is reused).

3. **Abstraction Layers.** Each layer presents a different abstraction
   from the layers above and below. Eliminate pass-through methods and
   pass-through variables. Pull complexity down into modules rather
   than pushing it up to callers; internal representation should
   differ from the external interface.

4. **Cohesion & Separation.** Together-or-apart decisions matter at
   every scope. Combine code that shares information, is always
   co-used, or can't be understood independently. Separate
   general-purpose mechanisms from special-purpose logic. Split
   methods to clarify abstractions, never just to shorten them.

5. **Error Handling.** Reduce the *places* where errors must be
   handled. Define errors out of existence by redesigning APIs so the
   "exceptional" case is normal. Mask exceptions at low levels;
   aggregate handling at high levels. Crash on unrecoverable errors
   instead of layering speculative recovery.

6. **Naming & Obviousness.** Names should make a reader's first guess
   correct. Avoid `data`, `info`, `count`, `status` — be precise
   (`fileBlock`, not `block`). Use a given name for one concept
   everywhere, and never reuse it for a different concept. Match
   reader expectations; document anything that violates them.

7. **Documentation.** Comments capture what code cannot: rationale,
   intent, invariants, units, null/edge semantics. Don't restate what
   the code already shows. Write interface docs while designing — it
   forces clearer abstractions. Cross-module design decisions live in
   obvious central locations, not buried in implementations.

8. **Strategic Design.** Working code is not enough. Invest ~10–20% of
   dev time in design quality; every modification should leave the
   design better than it was. Develop in increments of abstractions,
   not features. Avoid premature optimization, but stay aware of
   fundamentally expensive operations (network, disk, allocation,
   cache misses).

## Index

- [firmware-app.md](ARCHITECTURE/firmware-app.md) — board-agnostic firmware: state ring, gateway HTTP client, NTP, view orchestrator, semantic-action handlers.
- [firmware-hal.md](ARCHITECTURE/firmware-hal.md) — Hardware Abstraction Layer: `Display` / `InputSource` / `Board` interfaces + DNESP32S3B backend + ESP32-P4-7B Phase A stub.
- [gateway-api.md](ARCHITECTURE/gateway-api.md) — FastAPI surface: `/api/*` for devices, `/`, `/ui/*`, `/records*`, `/config`, `/sync` for the browser.
- [gateway-storage.md](ARCHITECTURE/gateway-storage.md) — persistence: SQLite `records` table and JSON config file with one-shot legacy migration.
- [gateway-openclaw.md](ARCHITECTURE/gateway-openclaw.md) — webhook poster + 60 s scheduler driving auto-sync and the 15 min auto-stop cap.
- [gateway-ui.md](ARCHITECTURE/gateway-ui.md) — server-rendered Records / Configuration page: feed-now panel, date-grouped records, live 1 Hz counter.

## Per-module template

Module files use the fixed template from the eatmycode skill: seven
sections in this order — **Goal**, **Status**, **Code Structure**,
**Key Types and Entry Points**, **Interactions**, **How to Test**,
**Open Gaps / Roadmap**. Headers are matched literally by the
verification step; do not paraphrase them.
