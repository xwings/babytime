# firmware-app

## Goal

Board-agnostic firmware logic: app state (feeding history ring, active
counter, pending-event queue), the gateway HTTP client (POST events,
poll `/api/state`, trigger `/api/sync`) running on Core 0, NTP setup,
view orchestration and 500 ms tickers, and the three semantic-action
handlers (`cycleView`, `toggleFeeding`, `manualSync`) wired to the
HAL's `InputSource`.

Infrastructure under every feature; no milestone gate.

## Status

`done`. Behaviour identical to the pre-HAL firmware on DNESP32S3B —
this file describes the post-refactor split, not a feature change.
ESP32-P4-7B inherits this layer unchanged; the touch redesign in
Phase B will swap which screen layouts the view orchestrator picks,
not what app state exists.

## Code Structure

| File | Role |
| ---- | ---- |
| `firmware/src/main.cpp` | Globals (declared in state.h), gateway HTTP + RTOS task, NTP, semantic-action handlers, `setup()`/`loop()` |
| `firmware/src/state.h` | Shared types + extern globals (history ring, active counter, mutex) and time/string helpers |
| `firmware/src/views.h` | View functions: `drawStatus`, `drawClockScreen`, `drawCounter`, `drawHistoryScreen`, `drawSyncStatus`, `redrawCurrentView` |
| `firmware/src/views.cpp` | View implementations against `hal::Display`; seven-segment renderer; layout derived from `display.width()/height()` |
| `firmware/include/config.h` | Wi-Fi SSID/pass, `GATEWAY_URL`, `GATEWAY_TOKEN`, `DEVICE_ID`, NTP offsets (overridden by `config.local.h`) |

## Key Types and Entry Points

- `firmware/src/state.h:17` — `enum ViewMode { VIEW_CLOCK, VIEW_HISTORY, VIEW_COUNTER }`.
- `firmware/src/state.h:19` — `struct FeedSession { startEpoch, stopEpoch }`.
- `firmware/src/state.h:26` — `struct ActiveCounter` — title, subtitle, base elapsed + start ms.
- `firmware/src/state.h:34-40` — extern globals (`currentView`, `feedHistory[]`, `feedHistoryCount`, `feedHistoryHead`, `activeCounter`, `gatewayOnline`, `stateMutex`).
- `firmware/src/main.cpp:33-39` — global definitions.
- `firmware/src/main.cpp:51-53` — `PendingEvent` + 16-slot `pendingQueue` (Core 1 producer, Core 0 consumer).
- `firmware/src/main.cpp:73-87` — `enqueuePendingEvent` (mutex-guarded, drops oldest on overflow).
- `firmware/src/main.cpp:90-100` — `setCounter` — flips view to `VIEW_COUNTER` and paints.
- `firmware/src/main.cpp:110-128` — `HttpSession` + `beginHttp` — TLS-aware `HTTPClient` factory.
- `firmware/src/main.cpp:130-144` — `gatewayPostEvent` — POST `/api/events`.
- `firmware/src/main.cpp:146-198` — `applyGatewayState` — reconciles local state from `/api/state`; **skips reconciliation while `pendingCount > 0`** so optimistic local edits aren't clobbered by stale server truth.
- `firmware/src/main.cpp:200-214` — `gatewayFetchState`.
- `firmware/src/main.cpp:216-225` — `gatewayTriggerSync` — POST `/api/sync`.
- `firmware/src/main.cpp:227-246` — `drainPendingQueue` — POST + pop loop.
- `firmware/src/main.cpp:248-256` — `gatewayTask` — Core 0 RTOS body; cadence = `GATEWAY_POLL_MS` (30 s).
- `firmware/src/main.cpp:260-265` — `cycleView` (PrimaryAction handler).
- `firmware/src/main.cpp:267-283` — `toggleFeeding` (SecondaryAction handler).
- `firmware/src/main.cpp:285-294` — `manualSync` (SyncRequest handler) — paints sync banner, posts, holds 2 s.
- `firmware/src/main.cpp:300-313` — `updateCounter` / `updateClockScreen` — 500 ms tickers driving live redraws.
- `firmware/src/main.cpp:340-371` — `connectWiFi` + NTP server lists.
- `firmware/src/main.cpp:380-407` — `setup()` — board init, callback wiring, Wi-Fi+NTP, gateway task spawn at Core 0.
- `firmware/src/main.cpp:409-417` — `loop()` — gateway-dirty redraw, tickers, `input().poll()`, 5 ms idle.
- `firmware/src/views.cpp:80-105` — `drawBigDigits` — seven-segment renderer with 500 ms colon heartbeat.
- `firmware/src/views.cpp:135-145` — `drawStatus`.
- `firmware/src/views.cpp:147-186` — `drawClockScreen` — time + date + IP + gateway online indicator.
- `firmware/src/views.cpp:188-225` — `drawCounter` — centered ASCII title + CJK subtitle + big digits + timestamp.
- `firmware/src/views.cpp:227-289` — `drawHistoryScreen` — date-grouped, numbered earliest-to-latest within each day.
- `firmware/src/views.cpp:291-298` — `drawSyncStatus` — full-screen banner.
- `firmware/src/views.cpp:300-318` — `redrawCurrentView` — view-state machine.

## Interactions

- Draws via [firmware-hal.md](firmware-hal.md): all paint calls go
  through `hal::currentBoard().display()`. Input events come from
  `hal::currentBoard().input()` after `setup()` registers
  callbacks.
- Talks to [gateway-api.md](gateway-api.md) over HTTP: POSTs
  `/api/events`, GETs `/api/state`, POSTs `/api/sync`.
- Optimistic local state (set immediately in `toggleFeeding`)
  reconciles when `applyGatewayState` next runs and the pending
  queue is empty.
- Concurrency: writes from `gatewayTask` (Core 0) take `stateMutex`;
  reads from `loop()`/`views.cpp` (Core 1) do not — pre-refactor
  contract preserved.

## How to Test

- `make build` — pass = PlatformIO prints `SUCCESS` with RAM/Flash
  usage summary (DEVICE defaults to `dnesp32s3b`).
- `make flash-monitor` — pass = serial shows, in order, `LCD init...`,
  `DHCP ok, IP=`, `NTP ok via <server>`, then `Gateway mode -> ...`
  (or `Standalone mode` when `GATEWAY_URL` is empty).
- On hardware: K1 short cycles view; K1 long (≥1.5 s) shows the
  sync banner and POSTs `/api/sync`; K2 toggles feeding and the
  counter view appears with a live 500 ms tick.

## Open Gaps / Roadmap

- ES8311 audio codec absent on this board variant; the alarm /
  voice-msg-to-gateway path is unimplemented.
- History view shows only the in-RAM 8-slot ring; full feeding log
  lives in the gateway and is reachable only via the web UI.
- No retry/backoff for `gatewayFetchState` beyond the next 30 s
  tick.
- Reads on Core 1 don't lock `stateMutex` (preserves pre-refactor
  behavior). Symptom would be torn `String` reads on the counter
  title/subtitle during a gateway-driven state swap; fix is to lock
  around `redrawCurrentView` in `loop()` if it ever shows up.
