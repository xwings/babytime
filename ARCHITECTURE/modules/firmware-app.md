---
eatmycode_version: "2.1.0"
---
# Firmware Application

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `firmware/src/main.cpp`, `state.h`, `views.*`, private firmware configuration, device state or gateway HTTP behavior.

## Responsibility and Status

Implemented board-independent tracker; status **in progress**: no build or
hardware check ran in this refresh (PlatformIO absent, no local `config.h`).
Owns RAM state, the feeding End action, gateway synchronization, Wi-Fi/NTP
and view composition. Board pins, LCD controllers and raw input belong to
HAL. Audio is unimplemented.

## Code Map

| Path / symbol | Role |
| --- | --- |
| `firmware/src/main.cpp`: `setup`, `gatewayTask`, `applyGatewayState`, `logFeedingEnd`, `cycleView` | Globals, startup, Wi-Fi/NTP, HTTP task, state decode, feeding action, tickers. |
| `firmware/src/state.h`: `FeedSession`, `ActiveCounter`, `ViewMode`, `gatewayMode()` | Shared externs, eight-entry history ring, totals, alert fields, mutex. |
| `firmware/src/views.{h,cpp}`: `drawClockScreen`, `drawHistoryScreen`, `drawCounter`, `redrawCurrentView` | Clock, date-grouped history, counter and status rendering through HAL. |
| `firmware/include/config.local.example.h` | Public macro surface; `config.h` and `config.local.h` are ignored local prerequisites. |

## Local Conventions

Use [root conventions](../../ARCHITECTURE.md#code-conventions). Observed:
Arduino `String`, camelCase helpers, fixed arrays, `constexpr` capacities
and an anonymous namespace for private app state. UI draws only through
`hal::Display`; board-specific code stays outside main/views. Shared
externs are declared in `state.h` and defined once in `main.cpp`.

## Contracts and Invariants

- Macros: `WIFI_SSID`, `WIFI_PASSWORD`, `GATEWAY_URL`, `GATEWAY_TOKEN`,
  `DEVICE_ID`, `GATEWAY_POLL_MS`, `FEEDING_DURATION_MINUTES` (`#ifndef`
  fallback 15 in `main.cpp`), optional `GATEWAY_CA_CERT`,
  `NTP_GMT_OFFSET_SEC`, `NTP_DST_OFFSET_SEC`. Sources include `config.h`;
  the example and README describe `config.local.h`, and no tracked header
  bridges them. `gatewayMode()` is `GATEWAY_URL[0] != '\0'`.
- `setup` allocates `stateMutex`, initializes the board, binds
  Primary=`cycleView` and Secondary=`logFeedingEnd`, connects Wi-Fi (20 s
  STA, 10 s DHCP; failure draws a status and skips NTP), tries CN then
  global NTP servers for 6 s each via `configTime`, and creates the
  `gateway` task (16 KB stack, priority 1, core 0) only in gateway mode.
  `loop` handles dirty redraws, tickers and input polling with a 5 ms delay.
- Wire contract: POST `GATEWAY_URL/api/events` JSON
  `{type:"log", device_id, timestamp_epoch}` with a Bearer header when a
  token is set. GET `/api/state` decodes `active.start_epoch`, `history[]`
  (`start_epoch`, `stop_epoch|null`, `activity`, `volume_ml`; newest first,
  reversed into the ring), `last_feeding.stop_epoch`, `today_feeds`,
  `today_ml`, `feeding_duration_minutes` (overrides the compile default)
  and `feeding_alert{due, elapsed_seconds, threshold_minutes}`. Any 2xx
  passes; Wi-Fi down fails both at once. One trailing URL `/` is stripped.
- `logFeedingEnd` updates local history and Last fed, resets alert due and
  elapsed, derives Start from the feeding duration and queues a `log`
  event. It never starts a timer. Today's totals are written only by
  `applyGatewayState`, so the Counter totals stay 0 in standalone mode.
- Eight mixed-activity RAM records hold an 11-byte usable label and milk
  amount only. Sixteen mutex-guarded pending events are volatile: overflow
  drops the oldest, a failed POST keeps the head for the next poll, and
  `/api/state` reconciles only while the queue is empty, so optimistic
  offline edits survive. No durable queue or event ID exists, so reboot
  loss and duplicate retry delivery are possible.
- HTTP uses a 3 s timeout and `GATEWAY_POLL_MS` cadence. `GATEWAY_CA_CERT`
  enables CA verification, otherwise `setInsecure()`. `gatewayOnline` is
  the last state-fetch result, shown in the Clock footer in gateway mode.
- Gateway-task state writes take `stateMutex`; loop/view reads do not. This
  is an observed race risk, not a synchronization model to extend. Dirty
  flags request redraw; the task never renders.
- `cycleView` goes Clock → History → Counter, skipping Counter while
  `activeCounter.active` is false; `redrawCurrentView` falls back to Clock.
  Clock and Counter tick at 500 ms, the alert ticker redraws History only,
  and idle Clock/Last fed alternate every 5 s. Alert rows flash on 500 ms
  `millis()` parity. Clock/date text refuses years before 2024.
- Time is NTP with fixed GMT/DST offsets; the gateway uses an IANA zone, so
  both must agree for matching day labels. History groups feeding by End
  and other activities by Start, renders `HH:MM-HH:MM act` (open
  `HH:MM-...`, point `HH:MM act`) and does not replicate gateway midnight
  splitting; synchronization replaces RAM.

## Dependencies and Boundaries

[HAL](firmware-hal.md) provides display/input/board and owns toolchain
selection; read it for rendering, font-origin or action-interface changes.
Read [API](gateway-api.md) for event/state payload, auth, feeding-duration
or calendar changes. Gateway owns durable records; the optimistic cache
must not overwrite server state while events remain unsent.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| --- | --- | --- |
| Event/state payload | HTTP serialization, queue, state decoder | API owner; failed POST/retry and pending-state protection. |
| State / concurrency | Shared globals, mutex sites, views | Both builds; hardware state swaps without torn reads. |
| Layout / input action | Views, tickers, handlers | HAL owner; clock/history/counter on each real target. |
| Config / NTP / TLS | Public example, startup and transport | Build without exposing credentials; standalone and gateway behavior. |

## Verification

Run both root firmware build commands; pass is PlatformIO SUCCESS with
resource summaries. Supply an off-PATH binary with `make ... PIO=/path`.
This refresh ran no build: `pio` is not installed here and
`firmware/include/` holds only the example header, so fresh-clone
reproducibility is unproven.

Hardware checks need a connected board: `make monitor DEVICE=dnesp32s3b`
after flashing. Pass evidence: LCD then DHCP/NTP status, K1 cycling views,
K2 producing one completed feed with derived Start, 500 ms ticks, the 5 s
idle switch and, with a disposable gateway, queued delivery after a network
drop before state reconciliation. Build output is not evidence for these.

## Known Gaps

The `config.h` include versus the documented `config.local.h` is an
undocumented local bridge; the tracked example alone is not a fresh-clone
build contract. Core-1 unlocked reads may tear shared Strings. Pending
queue loss and retry duplication are untested. No fetch backoff exists
beyond the poll interval. TLS verification is optional, and time-sync
failure does not block logging. Standalone mode never fills today's totals.
`main.cpp` still mentions "three semantic-action handlers" and defines an
unreferenced `K1_LONG_PRESS_MS`; only two actions exist. Grams and rich
activity detail are absent from device history. No hardware test suite.
