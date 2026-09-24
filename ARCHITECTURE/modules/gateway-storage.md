---
eatmycode_version: "2.1.0"
---
# Gateway Storage

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `gateway/app/db.py`, `gateway/app/config.py`, schemas, activity settings or migrations.

## Responsibility and Status

Persistence; status **in progress** for verification coverage
(feeding migration/config tests; other storage paths lack dedicated tests). Owns SQLite
records/day notes and JSON configuration. HTTP validation and calendar
splitting belong to the API; no durable event queue lives here.

## Code Map

| Path / symbol | Role |
| --- | --- |
| `gateway/app/db.py`: `init`, `get_active`, `stop_active`, `clone_segments`, `feeding_totals` | Schema creation, additive intake/category migrations, record/session/day-note CRUD and feeding aggregates. |
| `gateway/app/config.py`: `DEFAULTS`, `load`, `update`, `activity_list`, `int_value` | Defaults, cached atomic JSON settings, alias normalization, option/CIDR/int parsing, legacy migration. |
| `gateway/docker-compose.yml`, `gateway/Dockerfile` | Source of persistence env names; runtime owner is [API](gateway-api.md). |

## Local Conventions

Follow the [root baseline](../../ARCHITECTURE.md#code-conventions): private
lock/cache, `sqlite3.Row` dicts, parameterized SQL and allowlisted updates.
`_coerce` makes settings strings (bool → "1"/"0", None → ""). Use config parsers.

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
  '', feeding_type, solid_food_type, created_at)` with the single index `idx_records_start(start_epoch
  DESC)`; `day_notes(date PK, note, updated_at)`. `init` runs `CREATE IF
  NOT EXISTS`, then adds missing `volume_g`, `feeding_type`, `solid_food_type`.
  Legacy feeding/water rows become solid_food/water with NULL amounts and
  feeding_type; completed timestamps/metadata survive, open water closes at
  Start. Migration is idempotent. The legacy `config` table is never dropped.
- Helpers: `create_record` returns an id; `get_active(activity=None)` finds
  the newest open row; `stop_active(stop, activity=None)` closes it and returns
  bool; `update_record(rid, **fields)` drops unknown keys; `delete_record`;
  `list_records(limit, ids, offset, activity)` orders by
  `COALESCE(stop, start) DESC`, ignores the other filters when `ids` is
  given and applies `offset` only with `limit`; `count_records` has no
  callers; `get_day_notes(dates)`, `set_day_note`.
- `stop_epoch=NULL` means open. One-active-per-type is not a database constraint. `clone_segments` copies
  activity/category/notes/device but neither intake column and returns early on an
  empty list or missing id.
- `feeding_totals` counts `volume_ml IS NOT NULL` rows (zero included) in a
  half-open End range, excluding `feeding_type='water'`; API day summaries use truthy volume for `feeds`, so
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
  120; `default_volume_ml` ""; `default_feeding_type` formula; `default_language` en; `poopoo_amount_options`
  many,less; `poopoo_color_options` yellow,green; `poopoo_texture_options`
  soft,hard; `supplement_options` AD,D3; `solid_food_options` empty; `timezone` UTC; `ui_show_count` 10;
  `trusted_networks` 10.0.0.0/8; `trusted_proxies` "".
- `canonical_activity` casefolds aliases (`milk`, `solid food`, `solidfood`,
  `subpliment`). `activity_list` always starts with `feeding`, `solid_food`
  and keeps custom names. `timed_activities` drops Milk/Food/Poopoo/Supplement,
  adds `etc` whenever it is a configured type, and never removes `sleep`.
- `FEEDING_TYPES` is formula,breastfeeding; invalid defaults (including old
  water) fall back to formula. Unclassified legacy milk categories stay NULL.
- Food options are ordered, deduplicated comma/newline lists; reserved Water
  is excluded from configurable names and supplied by the UI. NULL food type
  means generic food, `water` means quantity-free water, other values are names.
- Poopoo/Supplement options are ordered, deduplicated comma/newline lists
  (`poopoo_options` keyed by `POOPOO_OPTION_KEYS`). Invalid CIDRs are dropped.
  `int_value(cfg, key, default, minimum)` clamps; `feeding_alert_minutes`
  and `feeding_duration_minutes` wrap it. `timezone`, `ui_show_count`,
  `default_volume_ml` and `default_language` are read raw by the API, and
  the scheduler parses `auto_stop_minutes` itself.

## Dependencies and Boundaries

Stdlib-only persistence. Read [API](gateway-api.md) and
[Scheduler](gateway-scheduler.md) for helper/time changes, [UI](gateway-ui.md)
for settings/options. No route imports belong here.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| --- | --- | --- |
| Add/change column | `init`, CRUD allowlists, cloning | Migration from older DB + fresh DB; API and affected clients. |
| Settings / activity aliases | Defaults, coercion, parsing, migration, scheduler's own parse | Reload/round-trip and old config; UI/API/scheduler owners. |
| Session / day aggregation | Active helpers, ordering, totals | Simultaneous types, midnight split, zero/blank intake. |

## Verification

Run root syntax/unittest checks. Sleep tests exercise storage through routes
with disposable state. Isolated stdlib smoke from root:

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

Feeding tests cover old-schema/category migrations, config defaults/options,
category CRUD and separate water totals. Legacy config migration, ordering,
deletion and other parsing lack dedicated tests.

## Known Gaps

Multi-helper changes (split rows,
bulk edits) are not one transaction. Locks/cache are process-local;
multi-worker coordination and concurrent first connection creation are
unverified. The fixed `.tmp` JSON path is not a multi-process write
protocol. Parsing tolerates errors, so bad timezone/CIDR input silently
changes behavior. Intake validation remains an API gap.
