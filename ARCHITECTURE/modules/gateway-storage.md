---
eatmycode_version: "2.1.0"
---
# Gateway Storage

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `gateway/app/db.py`, `gateway/app/config.py`, schemas, activity settings or migrations.

## Responsibility and Status

Implemented persistence; status **in progress** for verification coverage
(no dedicated storage tests; `config.py` is untested). Owns SQLite
records/day notes and JSON configuration. HTTP validation and calendar
splitting belong to the API; no durable event queue lives here.

## Code Map

| Path / symbol | Role |
| --- | --- |
| `gateway/app/db.py`: `init`, `get_active`, `stop_active`, `clone_segments`, `feeding_totals` | Schema creation, additive `volume_g` migration, record/session/day-note CRUD and feeding aggregates. |
| `gateway/app/config.py`: `DEFAULTS`, `load`, `update`, `activity_list`, `int_value` | Defaults, cached atomic JSON settings, alias normalization, option/CIDR/int parsing, legacy migration. |
| `gateway/docker-compose.yml`, `gateway/Dockerfile` | Source of persistence env names; runtime owner is [API](gateway-api.md). |

## Local Conventions

The [root baseline](../../ARCHITECTURE.md#code-conventions) suffices. Observed:
module-private lock/cache, `sqlite3.Row` results returned as dicts,
parameterized SQL and an allowlisted update column set. JSON setting values
are coerced to strings (`_coerce`: bool → "1"/"0", None → ""). Parse
user-edited values through the config helpers, never raw.

## Contracts and Invariants

- `GATEWAY_DB_PATH` (default `/babytime/gateway.db`) and
  `GATEWAY_CONFIG_PATH` (default `/babytime/config.json`) are read **once
  at import** into `db._DB_PATH` and `config.CONFIG_PATH`; tests patch
  `db._DB_PATH`/`db._conn` or set the environment before import. `TZ` is
  not read by Python; calendar behavior uses config `timezone`.
- `get_conn` lazily opens one cached connection (parent dir created, WAL,
  foreign keys, `check_same_thread=False`) with no lock around first
  creation; `_lock` serializes helper bodies and each write commits.
- Schema: `records(id PK AUTOINCREMENT, start_epoch NOT NULL, stop_epoch,
  volume_ml, volume_g, notes, activity DEFAULT 'feeding', device_id DEFAULT
  '', created_at)` with the single index `idx_records_start(start_epoch
  DESC)`; `day_notes(date PK, note, updated_at)`. `init` runs `CREATE IF
  NOT EXISTS`, then probes `table_info` to add `volume_g`; no version table
  exists. A legacy `config` table is read by `legacy_config_rows` and never
  dropped.
- Helpers: `create_record(start, stop=None, volume_ml, volume_g, notes,
  activity='feeding', device_id='') -> id`; `get_active(activity=None)`
  newest open row, optionally of one activity; `stop_active(stop,
  activity=None) -> bool` closes the newest open row; `update_record(rid,
  **fields)` silently drops unknown keys; `delete_record`;
  `list_records(limit, ids, offset, activity)` orders by
  `COALESCE(stop, start) DESC`, ignores the other filters when `ids` is
  given and applies `offset` only with `limit`; `count_records` has no
  callers; `get_day_notes(dates)`, `set_day_note`.
- `stop_epoch=NULL` means open. One-active-per-type is a caller
  convention, **not** a uniqueness constraint. `clone_segments` copies
  activity/notes/device but neither intake column and returns early on an
  empty list or missing id.
- `feeding_totals` counts `volume_ml IS NOT NULL` rows (zero included) in a
  half-open End range; API day summaries use truthy volume for `feeds`, so
  the two counters differ at zero.
- `set_day_note` trims and deletes blank entries (upsert refreshes
  `updated_at`); date validation belongs to the HTTP boundary.
- `load` returns defaults merged with the cache, writing a defaults file
  when none exists; malformed or non-object JSON falls back to defaults.
  Unknown keys are preserved (DEFAULTS is not an allowlist). `update` locks
  a re-read/merge/atomic `os.replace` of `<path>.tmp` and refreshes the
  cache; external edits are absorbed only by the next `update`.
  `migrate_from` seeds `{**DEFAULTS, **legacy}` once, when the file is absent.
- `DEFAULTS`: `activity_types` feeding,solid_food,sleep,poopoo,supplement,etc;
  `timed_activities` sleep,etc; `auto_stop_minutes` 15; `feeding_alert_minutes`
  120; `default_volume_ml` ""; `default_language` en; `poopoo_amount_options`
  many,less; `poopoo_color_options` yellow,green; `poopoo_texture_options`
  soft,hard; `supplement_options` AD,D3; `timezone` UTC; `ui_show_count` 10;
  `trusted_networks` 10.0.0.0/8; `trusted_proxies` "".
- `canonical_activity` casefolds aliases (`milk`, `solid food`, `solidfood`,
  `subpliment`). `activity_list` always starts with `feeding`, `solid_food`
  and keeps custom names. `timed_activities` drops Milk/Food/Poopoo/Supplement,
  adds `etc` whenever it is a configured type, and never removes `sleep`.
- Poopoo/Supplement options are ordered, deduplicated comma/newline lists
  (`poopoo_options` keyed by `POOPOO_OPTION_KEYS`). Invalid CIDRs are dropped.
  `int_value(cfg, key, default, minimum)` clamps; `feeding_alert_minutes`
  and `feeding_duration_minutes` wrap it. `timezone`, `ui_show_count`,
  `default_volume_ml` and `default_language` are read raw by the API, and
  the scheduler parses `auto_stop_minutes` itself.

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
| Settings / activity aliases | Defaults, coercion, parsing, migration, scheduler's own parse | Reload/round-trip and old config; UI/API/scheduler owners. |
| Session / day aggregation | Active helpers, ordering, totals | Simultaneous types, midnight split, zero/blank intake. |

## Verification

Run the root syntax check and unittest command: `gateway/tests/test_sleep.py`
exercises `init`, `create_record`, `get_active`, `stop_active`,
`clone_segments`, `list_records(ids=)` and `update_record` through HTTP
handlers with `db._DB_PATH`/`db._conn` patched. This isolated stdlib smoke
runs from root (passed in this refresh):

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

Untested: the `volume_g` migration on an old schema, legacy config
migration, `feeding_totals`, `COALESCE` ordering, `delete_record`, the
update allowlist and all `config.py` parsing. Schema changes need an
old-schema fixture.

## Known Gaps

No dedicated storage or config tests. Multi-helper changes (split rows,
bulk edits) are not one transaction. Locks/cache are process-local;
multi-worker coordination and concurrent first connection creation are
unverified. The fixed `.tmp` JSON path is not a multi-process write
protocol. Parsing tolerates errors, so bad timezone/CIDR input silently
changes behavior. `count_records` is dead code. Intake range validation
remains an API gap.
