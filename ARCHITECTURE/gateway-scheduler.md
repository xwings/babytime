# gateway-scheduler

## Goal

Background safety net that keeps the gateway honest while no human or
device is poking it: auto-stop any active session that has been running
longer than the configured `auto_stop_minutes` cap (default 15). This
guards against a device that started a session and then dropped off the
network without ever sending the `stop`.

## Status

`done`.

## Code Structure

| File | Role |
| ---- | ---- |
| `gateway/app/scheduler.py` | Auto-stop helper + the 60 s scheduler loop |

## Key Types and Entry Points

- `gateway/app/scheduler.py:7` — `_enforce_auto_stop(cfg)` — caps the
  active session at `start_epoch + minutes * 60`; writes
  `stop_epoch = cap` (a clean cap, not "now") and logs
  `[scheduler] auto-stopped session <id> at <N>min cap`. A
  non-positive `auto_stop_minutes` disables it.
- `gateway/app/scheduler.py:23` — `scheduler_loop()` — `async` task:
  wakes every 60 s and calls `_enforce_auto_stop`. Cancellable via
  `asyncio.CancelledError`.

## Interactions

- Reads/writes through [gateway-storage.md](gateway-storage.md):
  `get_active`, `stop_active`.
- Launched once at startup by `lifespan` in
  [gateway-api.md](gateway-api.md) via
  `asyncio.create_task(scheduler_loop())`; cancelled on shutdown.
- Auto-stop side-effect propagates to firmware through the normal
  `/api/state` polling path — no out-of-band signal.

## How to Test

With the gateway running, start a session, set the cap to 1 minute,
and watch the scheduler log:

```sh
curl -s -X POST http://localhost:8080/api/events \
  -H 'Content-Type: application/json' \
  -d '{"type":"start","device_id":"test"}'
curl -s -X POST http://localhost:8080/config \
  -d 'auto_stop_minutes=1'
sleep 90
docker compose logs gateway | grep auto-stopped
curl -s http://localhost:8080/api/state | jq '.active'
```

- Pass = the `logs` line contains
  `[scheduler] auto-stopped session <id> at 1min cap`.
- Pass = `.active` is `null` after the cap fires.

## Open Gaps / Roadmap

- 60 s scheduler tick → up to ~60 s overshoot vs. the configured
  cap. Acceptable for the 15 min default; sloppy if someone sets
  `auto_stop_minutes=1`. Would need a sub-minute tick or per-session
  timer to tighten.
