# gateway-openclaw

## Goal

Outbound integration with OpenClaw plus the background scheduler that
keeps the gateway honest while no human or device is poking it:

- Render and POST feeding records to the configured OpenClaw webhook,
  on demand (`/api/sync`, `/sync`) or on an `auto_sync_hours`
  interval.
- Auto-stop any active session that has been running longer than the
  configured `auto_stop_minutes` cap (default 15).

## Status

`done`.

## Code Structure

| File | Role |
| ---- | ---- |
| `gateway/app/openclaw.py` | Webhook payload rendering, POST, auto-stop helper, scheduler loop |

## Key Types and Entry Points

- `gateway/app/openclaw.py:14` — `render_message(records, cfg)` — applies the user's `webhook_message_template` and per-record `webhook_record_format`.
- `gateway/app/openclaw.py:61` — `send_sync(record_ids=None)` — selects records (explicit ids, or newest `webhook_default_sync_count`), POSTs to `openclaw_url` with `Authorization: Bearer <webhook_token>`.
- `gateway/app/openclaw.py:114` — `_enforce_auto_stop(cfg)` — caps active session at `start_epoch + minutes * 60`; writes `stop_epoch = cap` (clean cap, not "now") and logs `[scheduler] auto-stopped session <id> at <N>min cap`.
- `gateway/app/openclaw.py:130` — `scheduler_loop()` — `async` task: wakes every 60 s, always calls `_enforce_auto_stop`, then triggers `send_sync()` when `auto_sync_enabled` is truthy and `auto_sync_hours` have passed since the last fire. Cancellable via `asyncio.CancelledError`.

## Interactions

- Reads/writes through [gateway-storage.md](gateway-storage.md):
  `get_active`, `stop_active`, `list_records`.
- Invoked from [gateway-api.md](gateway-api.md) on `/api/sync` and
  `/sync`; launched once at startup by `lifespan` via
  `asyncio.create_task(scheduler_loop())`.
- Auto-stop side-effect propagates to firmware through the normal
  `/api/state` polling path — no out-of-band signal.

## How to Test

With the gateway running, start a session, set the cap to 1 minute,
and watch the scheduler log:

```sh
curl -s -X POST http://localhost:8080/api/events \
  -H 'Content-Type: application/json' \
  -d '{"type":"start","device_id":"test"}'
curl -s -X POST http://localhost:8080/api/config \
  -H 'Content-Type: application/json' \
  -d '{"auto_stop_minutes":"1"}'
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
- No retry/backoff on `send_sync` failure beyond the next interval;
  a transient OpenClaw outage drops that tick's payload silently.
- No metric of "last successful sync" exposed in the UI.
