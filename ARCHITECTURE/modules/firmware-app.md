---
eatmycode_version: "2.0.0"
---
# Firmware Application

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `firmware/src/main.cpp`, `state.h`, `views.*`, private firmware configuration, device state or gateway HTTP behavior.

## Responsibility and Status

Implemented board-independent tracker; status **in progress** for runtime
verification. Local builds succeed for both configured boards; no hardware
behavior is certified by the documentation refresh. Owns RAM state, feeding
end actions, gateway synchronization, NTP and view composition. Board pins,
LCD controllers and raw input belong to HAL. Audio is unimplemented.

## Code Map

| Path / symbol | Role |
| --- | --- |
| `firmware/src/main.cpp`: `setup`, `gatewayTask`, `applyGatewayState`, `logFeedingEnd` | Globals, startup, HTTP task, synchronization, feeding action, time helpers and tickers. |
| `firmware/src/state.h`: `FeedSession` | Shared state types, eight-entry history, counters and mutex declarations. |
| `firmware/src/views.{h,cpp}` | Clock, counter, date-grouped activity history and seven-segment rendering through HAL. |
| `firmware/include/config.local.example.h`, `.gitignore` | Public configuration example; `config.h` and `config.local.h` are ignored local prerequisites. |

## Local Conventions

Use [root conventions](../../ARCHITECTURE.md#code-conventions). Observed:
Arduino `String`, camelCase helpers, fixed arrays, `constexpr` capacities
and an anonymous namespace for private app state. UI draws only through
`hal::Display`; board-specific code stays outside main/views. Shared
externs are declared in `state.h` and defined once in `main.cpp`.

## Contracts and Invariants

- `setup` allocates the mutex, initializes the selected board/backlight,
  binds Primary=cycle view and Secondary=log feeding End, connects Wi-Fi/NTP,
  and creates a Core-0 gateway task only when `GATEWAY_URL` is nonempty.
  `loop` handles dirty redraws, ticks and polling with a 5 ms idle delay.
- Button logging immediately updates local history and Last fed, clears the
  alert, derives Start from configured feeding duration and queues a `log`
  event in gateway mode. It never starts a new feeding timer. Legacy open
  feeding is normalized; gateway duration overrides the compile default.
- Eight mixed-activity RAM records use an 11-byte usable activity label and
  milk amount only; no grams field exists. Gateway history arrives newest
  first and is reversed into the ring. Last feeding/today's totals are
  separate gateway fields, not inferred from the newest mixed activity.
- Sixteen pending events are mutex-guarded, volatile RAM; overflow drops the
  oldest. A failed POST leaves the event for a later poll. Successful POST
  removes the head; `/api/state` reconciles only while the queue is empty,
  preserving optimistic edits while offline. No durable queue or event ID
  exists, so reboot loss and duplicate retry delivery remain possible.
- HTTP operations use a 3-second timeout and `GATEWAY_POLL_MS` cadence
  (30-second public example). HTTPS transport and HTTPClient share scope;
  `GATEWAY_CA_CERT` enables CA verification, otherwise `setInsecure()` is
  called. A configured token becomes a Bearer header.
- Gateway-task state writes take `stateMutex`; loop/view reads currently do
  not. This is an observed race risk, not an approved synchronization model
  to extend. Dirty flags request redraw; the task does not render directly.
- Clock/counter/alert redraw at 500 ms; idle Clock and Last fed alternate at
  five seconds. History and active feeding remain under explicit control.
  Time is NTP-derived with configured fixed GMT/DST offsets; gateway uses
  an IANA zone, so those configurations must agree for matching day labels.
- Views measure HAL dimensions and use ASCII/CJK font styles, but digit
  sizes/footer hints are still oriented to the DNESP32S3B layout. Firmware
  groups feeding by End and other activities by Start. It does not implement
  the gateway's midnight splitting locally; synchronization replaces RAM.

## Dependencies and Boundaries

[HAL](firmware-hal.md) provides display/input/board and owns toolchain
selection; read it for rendering or action-interface changes. Read
[API](gateway-api.md) for event/state payload, auth, feeding-duration or
calendar changes. Gateway owns durable records; firmware's optimistic
cache must not overwrite server state while events remain unsent.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| --- | --- | --- |
| Event/state payload | HTTP serialization, queue, state decoder | API owner; failed POST/retry and pending-state protection. |
| State / concurrency | Shared globals, mutex sites, views | Both builds; hardware state swaps without torn reads. |
| Layout / input action | Views, tickers, handlers | HAL owner; clock/history/counter on each real target. |
| Config / NTP / TLS | Public example, startup and transport | Build without exposing credentials; standalone and gateway behavior. |

## Verification

Run both root firmware build commands; pass is PlatformIO SUCCESS and
resource summaries. An installed off-PATH binary can be supplied through
`make ... PIO=/path/to/pio`. Both target builds passed locally during this
refresh using an existing ignored base configuration; this does not prove
fresh-clone reproducibility or working P4 hardware.

Hardware-only checks require a connected matching board: `make monitor
DEVICE=dnesp32s3b` after loading the intended firmware. Observe LCD then
DHCP/NTP initialization, K1 view cycling and K2 producing one completed
feed with derived Start. Verify 500 ms updates and five-second idle switch.
With a disposable gateway, disconnect/reconnect networking and verify
queued delivery before state reconciliation. No hardware was available
for those checks; do not treat build output as their pass evidence.

## Known Gaps

`main.cpp`/`state.h` require `config.h`, but Git excludes that file and only
tracks `config.local.example.h`; the example alone is not a complete
fresh-clone build contract. Core-1 unlocked reads may tear shared Strings.
Pending queue loss/retry duplication is untested. No extra fetch backoff
beyond the poll interval. TLS peer verification is optional, and time-sync
failure does not prevent logging. Grams and rich gateway activity detail
are absent from the small device history. There is no hardware test suite.
