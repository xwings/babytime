# firmware-app

## Goal

Board-agnostic firmware logic: app state (activity history ring, active
counter, pending-event queue), the gateway HTTP client (POST events,
poll `/api/state`) running on Core 0, NTP setup, view orchestration and
500 ms tickers, and the two semantic-action handlers (`cycleView`,
`toggleFeeding`) wired to the HAL's `InputSource`.

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
| `firmware/src/views.h` | View functions: `drawStatus`, `drawClockScreen`, `drawCounter`, `drawHistoryScreen`, `redrawCurrentView` |
| `firmware/src/views.cpp` | View implementations against `hal::Display`; seven-segment renderer; layout derived from `display.width()/height()` |
| `firmware/include/config.h` | Wi-Fi SSID/pass, `GATEWAY_URL`, `GATEWAY_TOKEN`, `DEVICE_ID`, NTP offsets (overridden by `config.local.h`) |

## Key Types and Entry Points

- `firmware/src/state.h:18` — `enum ViewMode { VIEW_CLOCK, VIEW_HISTORY, VIEW_COUNTER }`.
- `firmware/src/state.h:20` — `struct FeedSession { startEpoch, stopEpoch, activity[12], volumeMl }` — the history ring holds every activity type; `activity`/`volumeMl` drive the activity screen's per-row label and per-day ml total.
- `firmware/src/state.h:29` — `struct ActiveCounter` — title, subtitle, base elapsed + start ms.
- `firmware/src/state.h:37-46` — extern globals (`currentView`, `feedHistory[]`, `feedHistoryCount`, `feedHistoryHead`, `lastFeedingStop`, `todayFeeds`, `todayMl`, `feedingAlertDue`, `activeCounter`, `gatewayOnline`, `stateMutex`). `lastFeedingStop` is the stop epoch of the most recent feeding (0 = none), feeding the "Last fed" counter independently of the mixed-activity history ring; `todayFeeds`/`todayMl` are the gateway-computed daily feeding tally shown on the counter screen. `feedingAlertDue` mirrors `/api/state.feeding_alert.due` and drives the red-background blink.
- `firmware/src/main.cpp:26-38` — global definitions.
- `firmware/src/main.cpp:54` — `PendingEvent` + 16-slot `pendingQueue` (Core 1 producer, Core 0 consumer).
- `firmware/src/main.cpp:83` — `enqueuePendingEvent` (mutex-guarded, drops oldest on overflow).
- `firmware/src/main.cpp:99` — `setCounter` — flips view to `VIEW_COUNTER` and paints.
- `firmware/src/main.cpp:122` — `HttpSession` + `beginHttp` — TLS-aware `HTTPClient` factory.
- `firmware/src/main.cpp:145` — `gatewayPostEvent` — POST `/api/events`.
- `firmware/src/main.cpp:161` — `applyGatewayState` — reconciles local state from `/api/state`; **skips reconciliation while `pendingCount > 0`** so optimistic local edits aren't clobbered by stale server truth. Fills the history ring from `history` (all activities, incl. `activity`/`volume_ml`), caches `today_feeds`/`today_ml` and `feeding_alert`, then drives the live counter: open feeding (`active`) → "Feeding now"; else `last_feeding.stop_epoch` (→ `lastFeedingStop`) → "Last fed" or "Time to feed?" when the alert is due.
- `firmware/src/main.cpp:242` — `gatewayFetchState`.
- `firmware/src/main.cpp:259` — `drainPendingQueue` — POST + pop loop.
- `firmware/src/main.cpp:280` — `gatewayTask` — Core 0 RTOS body; cadence = `GATEWAY_POLL_MS` (30 s).
- `firmware/src/main.cpp:292` — `cycleView` (PrimaryAction handler).
- `firmware/src/main.cpp:302` — `toggleFeeding` (SecondaryAction handler).
- `firmware/src/main.cpp:325` — `updateCounter` / `updateClockScreen` / `updateAlertBlink` — 500 ms tickers driving live redraws and the history-screen alert blink.
- `firmware/src/main.cpp:348` — `updateIdleViewSwitch` — when feeding is idle and a completed feeding exists, automatically alternates Clock and Last fed counter views every 5 seconds; History and active-feeding counters are left under explicit user/action control.
- `firmware/src/main.cpp:394` — `connectWiFi` + NTP server lists.
- `firmware/src/main.cpp:474` — `setup()` — board init, callback wiring, Wi-Fi+NTP, gateway task spawn at Core 0.
- `firmware/src/main.cpp:497` — `loop()` — gateway-dirty redraw, tickers, `input().poll()`, 5 ms idle.
- `firmware/src/views.cpp:75` — `drawBigDigits` — caller-sized seven-segment renderer (`DigitMetrics`) with 500 ms colon heartbeat.
- `firmware/src/views.cpp:129` — `drawStatus`.
- `firmware/src/views.cpp:138` — `drawClockScreen` — time + date + IP + gateway online indicator (`CLOCK_DIGITS`); when `feedingAlertDue`, the header reads "Time to feed?" and the background alternates dark red/black.
- `firmware/src/views.cpp:177` — `drawCounter` — centered ASCII title + CJK subtitle + size-2 today's-feeding tally (`todayFeeds`/`todayMl`) + smaller `COUNTER_DIGITS` big digits + timestamp.
- `firmware/src/views.cpp:227` — `drawHistoryScreen` ("Activity") — date-grouped; each row is `start-stop activity`, and the date header carries the day's feeding-volume total (right-aligned ml).
- `firmware/src/views.cpp:300` — `redrawCurrentView` — view-state machine.

## Interactions

- Draws via [firmware-hal.md](firmware-hal.md): all paint calls go
  through `hal::currentBoard().display()`. Input events come from
  `hal::currentBoard().input()` after `setup()` registers
  callbacks.
- Talks to [gateway-api.md](gateway-api.md) over HTTP: POSTs
  `/api/events`, GETs `/api/state`.
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
- On hardware: K1 cycles view; K2 toggles feeding and the counter
  view appears with a live 500 ms tick. After feeding is stopped,
  Clock and Last fed alternate every 5 seconds while idle.

## Open Gaps / Roadmap

- ES8311 audio codec absent on this board variant; the alarm /
  voice-msg-to-gateway path is unimplemented.
- Activity view shows only the in-RAM 8-slot ring (all activity types);
  the full log lives in the gateway and is reachable only via the web UI.
- No retry/backoff for `gatewayFetchState` beyond the next 30 s
  tick.
- Reads on Core 1 don't lock `stateMutex` (preserves pre-refactor
  behavior). Symptom would be torn `String` reads on the counter
  title/subtitle during a gateway-driven state swap; fix is to lock
  around `redrawCurrentView` in `loop()` if it ever shows up.
