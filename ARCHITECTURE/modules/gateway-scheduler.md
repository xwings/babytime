---
eatmycode_version: "2.1.0"
---
# Gateway Scheduler

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `gateway/app/scheduler.py`, task lifespan or auto-stop semantics.

## Responsibility and Status

Implemented background session capping; status **in progress** because
multi-activity coverage is incomplete. Every 60 seconds it caps at most one
due record. It does not notify, poll devices or update browser state.

## Code Map

| Path / symbol | Role |
| --- | --- |
| `gateway/app/scheduler.py`: `_enforce_auto_stop`, `scheduler_loop` | Synchronous cap calculation/write inside an asyncio loop. |
| `gateway/app/main.py`: `lifespan` | Starts one task after `db.init` and config migration; cancels/awaits it on shutdown. |
| `gateway/app/util.py`: `SPLIT_ACTIVITIES`, `midnight_segments` | Gateway-local day boundary behavior, owned by [API](gateway-api.md). |

## Local Conventions

Use the [root baseline](../../ARCHITECTURE.md#code-conventions).
`_enforce_auto_stop` takes a config snapshot for deterministic checks and
parses `auto_stop_minutes` itself rather than through `config.int_value`.
The loop catches/prints exceptions per iteration and exits on
cancellation; diagnostics are `print` calls, not structured logging.

## Contracts and Invariants

- Each tick: `asyncio.sleep(60)` (first check 60 s after startup), then
  `config.load()`; `config.update` refreshes that cache, so UI edits apply
  on the next tick. `auto_stop_minutes` parses as int (`ValueError` → 15,
  `TypeError` falls to the loop's error print) and <=0 disables.
- Eligible set is `timed_activities(cfg) | {feeding} − {sleep}`, so `etc`
  is capped by default. One `get_active(activity)` query per eligible type;
  only the newest by `start_epoch` is evaluated (equal starts tie-break by
  set order). Sleep stays open until manually stopped and cannot block
  another activity's cap.
- Due when `int(time.time()) >= start + minutes*60` (patchable via
  `scheduler.time.time`). The stored stop is `midnight_segments(start, cap,
  activity, cfg timezone or UTC)[0][1]`, i.e. `min(cap, local midnight
  after start − 1)`; the write may land one tick late.
- `stop_active(stop, activity=)` re-queries the newest open row of that
  activity, which may differ from the evaluated row under a race. The
  following `clone_segments(id, segments[1:])` is a no-op while
  `SPLIT_ACTIVITIES == {"sleep"}`, because non-sleep clamps to one segment;
  keep the call as the guard for future split rules. No notification occurs.
- Failure prints `[scheduler] error: ...` and keeps the loop alive; success
  prints the record ID and configured minutes. Lifespan cancellation is
  awaited before exit.

## Dependencies and Boundaries

Reads configuration and persists through [Storage](gateway-storage.md);
read it when changing active lookup or transaction semantics. Read
[API](gateway-api.md) for time splitting or startup changes and keep the
same time normalization as HTTP writes (`main._segments` wraps the same
helper with the same timezone fallback). Browser changes appear on
reload; firmware observes state through normal polling.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| --- | --- | --- |
| Cap / selection | `_enforce_auto_stop`, active helper | Below/at/after cap, disabled/invalid values, feeding and concurrent types. |
| Cadence / shutdown | `scheduler_loop`, lifespan | Cancellation exits; an iteration error does not terminate the task. |
| Midnight handling | Segment helper + cloning | API/storage owners; sleep split versus first-day clamp. |

## Verification

`gateway/tests/test_sleep.py` covers cap exclusion with a concurrent
feeding (`test_sleep_does_not_prevent_other_timers_from_being_capped`) and
sleep left open (`test_manual_stop_splits_at_local_midnight`); run the root
unittest command. This deterministic root command (stdlib only) passed in
this refresh:

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

Pass proves before-cap preservation and the exact capped stop for one
session. Untested: disabled/invalid minutes, a cap crossing midnight,
newest-wins among several open records, custom timed types, loop
cadence, exception recovery and cancellation. Task startup/shutdown is
observed with the [manual gateway checks](../topics/gateway-manual-checks.md)
(read when verifying against a running gateway).

## Known Gaps

Older eligible sessions can remain open while a newer eligible one is
active; checking all due records per tick is outside this contract. Stop
and clone calls are separate transactions and lookup/write is not atomic.
`auto_stop_minutes` parsing is duplicated from `config.py`. The 60-second
cadence delays visible closure.
