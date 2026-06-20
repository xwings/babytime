# babytime

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
deployment: durable SQLite log, a web UI for editing records and
per-day notes, multiple devices sharing one source of truth, and a
JSON record API that a remote agent reads and writes directly (see
`skill/`).

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
  app/             Python source (main, db, config, scheduler, util)
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
   `toggleFeeding`) are then bound on
   `board.input()`, and Wi-Fi + NTP come up.
2. In gateway mode, `xTaskCreatePinnedToCore(gatewayTask, …, 0)`
   pins the HTTP client to Core 0.
3. `loop()` (Core 1) calls `board.input().poll()`, ticks the UI, and
   redraws when `gatewayStateDirty` is set by the Core 0 task.

**Gateway** (`gateway/Dockerfile`):

1. `docker compose up` → `uvicorn app.main:app --host 0.0.0.0 --port 8080`.
2. FastAPI's `lifespan` hook calls `db.init()`, runs the legacy
   config migration, and spawns `scheduler.scheduler_loop` as a
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

Behavioral guidelines to reduce common LLM coding mistakes. Merge with
project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For
trivial tasks, use judgment.

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If
yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make
it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs,
fewer rewrites due to overcomplication, and clarifying questions come
before implementation rather than after mistakes.

## Index

- [firmware-app.md](ARCHITECTURE/firmware-app.md) — board-agnostic firmware: state ring, gateway HTTP client, NTP, view orchestrator, semantic-action handlers.
- [firmware-hal.md](ARCHITECTURE/firmware-hal.md) — Hardware Abstraction Layer: `Display` / `InputSource` / `Board` interfaces + DNESP32S3B backend + ESP32-P4-7B Phase A stub.
- [gateway-api.md](ARCHITECTURE/gateway-api.md) — FastAPI surface: `/api/*` for devices and the record + day-note JSON API, `/`, `/ui/*`, `/records*`, `/config` for the browser.
- [gateway-storage.md](ARCHITECTURE/gateway-storage.md) — persistence: SQLite `records` + `day_notes` tables and JSON config file with one-shot legacy migration.
- [gateway-scheduler.md](ARCHITECTURE/gateway-scheduler.md) — 60 s background loop enforcing the `auto_stop_minutes` cap on runaway sessions.
- [gateway-ui.md](ARCHITECTURE/gateway-ui.md) — server-rendered Records / Configuration page: feed-now panel, date-grouped records, per-day notes, live 1 Hz counter.

## Per-module template

Module files use the fixed template from the eatmycode skill: seven
sections in this order — **Goal**, **Status**, **Code Structure**,
**Key Types and Entry Points**, **Interactions**, **How to Test**,
**Open Gaps / Roadmap**. Headers are matched literally by the
verification step; do not paraphrase them.
