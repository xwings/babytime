# gateway-storage

## Goal

Persistence for the gateway. Three stores:

- SQLite `records` table — durable activity log (start, stop, volume,
  notes, activity type, device id, created_at). `volume_ml` is only
  meaningful for the `feeding` activity.
- SQLite `day_notes` table — one free-text note per calendar date
  (`YYYY-MM-DD`), edited in the web UI or written by an agent over the
  JSON API.
- JSON config file (`config.json`) — user-editable settings written
  atomically; backwards-compatible with the legacy `config` SQLite
  table via one-shot migration on first boot.

## Status

`done`.

## Code Structure

| File | Role |
| ---- | ---- |
| `gateway/app/db.py` | SQLite connection, schema, record CRUD, active-session helpers, day-note get/set, legacy config reader |
| `gateway/app/config.py` | JSON-backed config: defaults, atomic write, in-memory cache, legacy migration |

## Key Types and Entry Points

- `get_conn()` — opens connection at `_DB_PATH` (env `GATEWAY_DB_PATH`, default `/babytime/gateway.db`).
- `init()` — `CREATE TABLE IF NOT EXISTS` + index.

  Schema:

  ```sql
  CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_epoch INTEGER NOT NULL,
    stop_epoch INTEGER,
    volume_ml INTEGER,
    notes TEXT,
    activity TEXT NOT NULL DEFAULT 'feeding',
    device_id TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_records_start ON records(start_epoch DESC);
  CREATE TABLE IF NOT EXISTS day_notes (
    date TEXT PRIMARY KEY,
    note TEXT NOT NULL DEFAULT '',
    updated_at INTEGER NOT NULL
  );
  ```

- `get_day_notes(dates=None)` — `{date: note}` map (all rows, or just the listed dates).
- `set_day_note(date, note)` — upsert one day's note; a blank note deletes the row, so "no note" and "empty note" collapse to one state.
- `legacy_config_rows()` — returns rows from any pre-existing `config` table; used by `config.migrate_from`.
- `get_active(activity=None)` — the open (`stop_epoch IS NULL`) session for that activity, or the most recent open session of any activity when `activity` is `None`; or `None`. One session may be open per activity type concurrently.
- `stop_active(stop_epoch=..., activity=None)` — close the open session for that activity (or the latest open one); returns truthy if a row was updated.
- `create_record(..., activity='feeding')` — insert. "At most one active per activity" is enforced by the caller (`api_post_event` / `ui_activity_toggle`) checking `get_active(activity)` first, not by this function.
- `update_record(id, **fields)` — inline UI edit path; `activity` is an allowed field.
- `delete_record(id)`.
- `list_records(limit=..., ids=..., offset=..., activity=...)` — newest-first pagination; `activity` filters to one type (e.g. `"feeding"` for the device-facing `/api/state` history).
- `count_records()`.
- `feeding_totals(start_epoch, stop_epoch)` — `{feeds, ml}` for feedings (with a volume) in a half-open start-epoch window; drives `/api/state`'s `today_feeds`/`today_ml` (caller passes local-midnight bounds).
- `gateway/app/config.py` — `DEFAULTS` — the 10 config keys with seed values: `activity_types`, `timed_activities`, `auto_stop_minutes`, `feeding_alert_minutes`, `default_volume_ml`, `default_language`, `timezone`, `ui_show_count`, `trusted_networks`, `trusted_proxies`.
- `activity_list(cfg)` — split/dedupe `activity_types`, always with `feeding` first; reused by the app + UI for dropdowns.
- `timed_activities(cfg)` — set of activities recorded as start→stop sessions (the rest are instant single-timestamp logs); always includes `feeding`. Used by the UI and scheduler to tell timed from instant activities.
- `load()` — returns merged-with-defaults dict from cache (lazy init from disk).
- `update(items)` — merges into the on-disk JSON via atomic `os.replace`, refreshes cache.
- `migrate_from(legacy_loader)` — seed `config.json` from the legacy SQLite `config` table on first start; no-op once the file exists. `CONFIG_PATH` env `GATEWAY_CONFIG_PATH` (default `/babytime/config.json`).

## Interactions

- Consumed on every route in [gateway-api.md](gateway-api.md).
- [gateway-scheduler.md](gateway-scheduler.md) reads `get_active` and
  writes via `stop_active` (auto-stop).

## How to Test

With the gateway running (`docker compose up -d --build`):

```sh
curl -s -X POST http://localhost:8080/api/events \
  -H 'Content-Type: application/json' \
  -d '{"type":"start","device_id":"test"}'
curl -s http://localhost:8080/api/state | jq '.active'
```

- Pass = the second call prints a JSON object describing the new
  session — proves `create_record` + `get_active`.

Then stop and re-check:

```sh
curl -s -X POST http://localhost:8080/api/events \
  -H 'Content-Type: application/json' \
  -d '{"type":"stop","device_id":"test"}'
curl -s http://localhost:8080/api/state | jq '{active:.active, last:.history[0]}'
```

- Pass = `.active == null` and the newly-finished session appears as
  `.last` (proves `stop_active` + `list_records`).

## Open Gaps / Roadmap

- No unit tests under `gateway/`; verification is curl-driven.
- No schema migrations beyond `CREATE TABLE IF NOT EXISTS`. Any
  column add requires manual SQL or a DB wipe.
- `config.json` writes are atomic per-call but there is no
  transactional grouping if the UI ever saves a multi-key batch
  that needs all-or-nothing semantics.
