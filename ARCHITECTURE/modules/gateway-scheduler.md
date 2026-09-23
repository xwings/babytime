---
eatmycode_version: "2.0.0"
---
# Gateway Scheduler

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `gateway/app/scheduler.py`, task lifespan or auto-stop semantics.

## Responsibility and Status

Implemented background session capping; status **in progress** because
multi-activity coverage is incomplete. It wakes every 60 seconds and checks
one open record. It does not send notifications, poll devices or update
browser state directly.

## Code Map

| Path / symbol | Role |
| --- | --- |
| `gateway/app/scheduler.py`: `_enforce_auto_stop`, `scheduler_loop` | Synchronous cap calculation/write inside an asyncio loop. |
| `gateway/app/main.py`: `lifespan` | Starts one task after database/config initialization and cancels/awaits it on shutdown. |
| `gateway/app/util.py`: `midnight_segments` | Shared gateway-local day boundary behavior, owned by [API](gateway-api.md). |

## Local Conventions

Use the [root baseline](../../ARCHITECTURE.md#code-conventions). `_enforce_auto_stop`
accepts a config snapshot for deterministic checks. The loop catches/logs
exceptions per iteration and exits on cancellation; these are observed
print-based diagnostics, not structured logging.

## Contracts and Invariants

- Sleep happens before each check. `auto_stop_minutes` parses as integer,
  defaults to 15 on invalid input, and disables enforcement at <=0.
- Selects the newest open record among legacy feeding and configured timed
  activities, excluding Sleep. Sleep stays open until manually stopped and
  cannot block another activity's cap. Only one eligible record is checked
  per iteration.
- A due session closes at `start + minutes*60`, not the tick's current time.
  The write may occur roughly one tick later; stored duration is capped.
- `midnight_segments` processes the cap before writing; eligible non-sleep
  activities clamp to the first day. `stop_active` closes the newest
  active row of the selected activity and `clone_segments` writes additional rows, dropping intake
  amounts. No notification side effect occurs.
- Failure prints `[scheduler] error: ...` and keeps the loop alive; a
  successful cap prints its record ID and configured minutes. FastAPI
  lifespan cancellation is awaited before exit.

## Dependencies and Boundaries

Reads configuration and persists through [Storage](gateway-storage.md).
Read that owner when changing active lookup/transaction semantics; read
[API](gateway-api.md) for time splitting or startup changes. Browser changes
appear on reload; firmware observes state through normal polling. The
scheduler must share the same time normalization as HTTP writes.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| --- | --- | --- |
| Cap / selection | `_enforce_auto_stop`, active helper | Below/at/after cap, disabled/invalid values, feeding and concurrent types. |
| Cadence / shutdown | `scheduler_loop`, lifespan | Cancellation exits; an iteration error does not terminate the task. |
| Midnight handling | Segment helper + cloning | API/storage owners; sleep split versus first-day clamp. |

## Verification

Root Python syntax check plus this deterministic root command (stdlib only):

```sh
PYTHONPATH=gateway python3 - <<'PY'
import os, tempfile
from unittest.mock import patch
with tempfile.TemporaryDirectory() as d:
    os.environ['GATEWAY_DB_PATH'] = d + '/db'
    from app import db, scheduler
    db.init()
    rid = db.create_record(100, activity='feeding')
    cfg = {'auto_stop_minutes': '1', 'timed_activities': 'sleep', 'timezone': 'UTC'}
    with patch.object(scheduler.time, 'time', return_value=159):
        scheduler._enforce_auto_stop(cfg)
    assert db.get_active()['id'] == rid
    with patch.object(scheduler.time, 'time', return_value=170):
        scheduler._enforce_auto_stop(cfg)
    assert db.get_active() is None
    assert db.list_records()[0]['stop_epoch'] == 160
    db.get_conn().close()
print('scheduler smoke passed')
PY
```

Pass proves before-cap preservation and exact capped stop for one session;
it does not establish whole-loop timing, exception recovery or hardware
propagation. Use the API owner's disposable gateway to check task startup
and shutdown; no real-session mutation is needed for this smoke.

## Known Gaps

`gateway/tests/test_sleep.py` verifies sleep cap exclusion and concurrent
feeding capping (run via the API owner's unittest command). Older eligible
sessions can remain open while a newer eligible one is active; checking all
due records in each tick remains outside this contract. Stop and clone calls are separate
transactions and lookup/write is not atomic. The 60-second cadence delays
visible closure; changing that is a behavior decision, not a docs fix.
