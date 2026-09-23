---
eatmycode_version: "2.0.0"
---
# Gateway Storage

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `gateway/app/db.py`, `gateway/app/config.py`, schemas, activity settings or migrations.

## Responsibility and Status

Implemented persistence; status **in progress** for verification coverage.
Owns SQLite records/day notes and JSON configuration. HTTP validation and
calendar splitting belong to the API; no durable event queue lives here.

## Code Map

| Path / symbol | Role |
| --- | --- |
| `gateway/app/db.py`: `init`, `clone_segments`, `feeding_totals` | Schema creation/additive grams migration, record/session/day-note operations and feeding aggregates. |
| `gateway/app/config.py`: `load`, `activity_list` | Defaults, cached atomic JSON settings, built-in activity normalization and parsing. |
| `gateway/docker-compose.yml`, `gateway/Dockerfile` | Persistence environment names; runtime/tooling owner is [API](gateway-api.md). |

## Local Conventions

The [root baseline](../../ARCHITECTURE.md#code-conventions) suffices. Observed:
module-private locks/cache, dict return values, parameterized SQL values and
allowlisted update columns. JSON setting values are coerced to strings.
Use config parsing helpers instead of assuming user-edited values are valid.

## Contracts and Invariants

- `GATEWAY_DB_PATH` defaults to `/babytime/gateway.db`; one cached SQLite
  connection uses WAL, foreign keys and `check_same_thread=False`. `_lock`
  serializes helper operations within one process; each write commits.
- `records` owns integer epoch bounds (`stop_epoch=NULL` means open), optional
  `volume_ml`/`volume_g`, notes, activity, device and creation time. `init`
  adds `volume_g` to older schemas; there is no general migration framework.
- `get_active(activity)` returns the newest open record of that activity;
  omitting it selects the newest open record overall. One-active-per-type
  is a caller convention, **not** a database uniqueness constraint.
- `list_records` orders by `COALESCE(stop_epoch,start_epoch)` descending.
  `clone_segments` copies activity/notes/device but neither intake column,
  so splitting never duplicates intake. Split halves have independent IDs.
- `feeding_totals` counts volume-bearing feedings (including zero ml) in a
  half-open End-time range. API day summaries use truthy volume for `feeds`;
  callers must not assume those two counters are equivalent at zero.
- `day_notes` keys are calendar-date strings. `set_day_note` trims text and
  deletes blank entries; date validation belongs to the HTTP boundary.
- `GATEWAY_CONFIG_PATH` defaults to `/babytime/config.json`. `load` returns a
  copy of defaults merged with cached values; malformed/non-object JSON
  falls back to defaults. `update` locks a read/merge/write and atomically
  replaces the file; external edits are not reloaded by cached readers.
  Migration seeds absent JSON from the legacy SQLite config table once.
- `config.DEFAULTS` is canonical for setting names/defaults. `activity_list`
  always starts with `feeding` and `solid_food`, normalizes known aliases
  and preserves custom names. `timed_activities` excludes Milk/Food/Poopoo/
  Supplement and includes configured `etc`; UI may still use a dialog.
- Poopoo amount/color/texture and Supplement choices are ordered, deduplicated
  comma/newline lists. Invalid CIDRs are ignored. `auto_stop_minutes` is both
  intake duration and session cap; `feeding_alert_minutes=0` disables alerts.

## Dependencies and Boundaries

Stdlib-only persistence. [API](gateway-api.md) and
[Scheduler](gateway-scheduler.md) consume helpers; read those owners when
changing call semantics, transactions or time fields. Read
[UI](gateway-ui.md) when changing settings/options rendered in forms.
No route imports or browser concerns belong in storage.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| --- | --- | --- |
| Add/change column | `init`, CRUD allowlists, cloning | Migration from older DB + fresh DB; API and affected clients. |
| Settings / activity aliases | Defaults, coercion, parsing, migration | Reload/round-trip and old config; UI/API owners. |
| Session / day aggregation | Active helpers, ordering, totals | Simultaneous types, midnight split, zero/blank intake. |

## Verification

Run root Python syntax check. This isolated stdlib smoke runs from root:

```sh
PYTHONPATH=gateway python3 - <<'PY'
import os, tempfile
with tempfile.TemporaryDirectory() as d:
    os.environ['GATEWAY_DB_PATH'] = d + '/db'
    os.environ['GATEWAY_CONFIG_PATH'] = d + '/config.json'
    from app import db, config
    db.init()
    rid = db.create_record(100, 160, volume_g=60, activity='solid_food')
    db.clone_segments(rid, [(170, 180)])
    rows = db.list_records()
    assert len(rows) == 2 and rows[0]['volume_g'] is None
    db.set_day_note('2026-09-23', ' note ')
    assert db.get_day_notes()['2026-09-23'] == 'note'
    db.set_day_note('2026-09-23', '')
    assert db.get_day_notes() == {}
    assert config.activity_list(config.update({'activity_types': 'sleep'})) == ['feeding', 'solid_food', 'sleep']
    db.get_conn().close()
print('storage smoke passed')
PY
```

Pass proves isolated CRUD/cloning/day-note/config basics, not concurrent
writes or a complete migration matrix. Schema changes also require an
old-schema fixture including the additive `volume_g` path.

## Known Gaps

No committed storage tests. Multi-helper changes (split rows, bulk edits)
are not one transaction. Locks/cache are process-local; multi-worker
coordination and concurrent first connection creation are unverified.
The fixed `.tmp` JSON path is not a multi-process write protocol. Configuration
parsing tolerates errors, so bad timezone/CIDR input can silently change
behavior. Intake range validation remains an API gap.
