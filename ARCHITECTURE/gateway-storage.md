# gateway-storage

## Goal

Persistence for the gateway. Two stores:

- SQLite `records` table — durable feeding log (start, stop, volume,
  notes, device id, created_at).
- JSON config file (`config.json`) — user-editable settings written
  atomically; backwards-compatible with the legacy `config` SQLite
  table via one-shot migration on first boot.

## Status

`done`.

## Code Structure

| File | Role |
| ---- | ---- |
| `gateway/app/db.py` | SQLite connection, schema, record CRUD, active-session helpers, legacy config reader |
| `gateway/app/config.py` | JSON-backed config: defaults, atomic write, in-memory cache, legacy migration |

## Key Types and Entry Points

- `gateway/app/db.py:11` — `get_conn()` — opens connection at `_DB_PATH` (env `GATEWAY_DB_PATH`, default `/feeding/gateway.db`).
- `gateway/app/db.py:22` — `init()` — `CREATE TABLE IF NOT EXISTS` + index.

  Schema (verbatim from `db.py:27-37`):

  ```sql
  CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_epoch INTEGER NOT NULL,
    stop_epoch INTEGER,
    volume_ml INTEGER,
    notes TEXT,
    device_id TEXT,
    created_at INTEGER NOT NULL
  );
  CREATE INDEX IF NOT EXISTS idx_records_start ON records(start_epoch);
  ```

- `gateway/app/db.py:42` — `legacy_config_rows()` — returns rows from any pre-existing `config` table; used by `config.migrate_from`.
- `gateway/app/db.py:58` — `get_active()` — the single `stop_epoch IS NULL` row, or `None`.
- `gateway/app/db.py:67` — `stop_active(stop_epoch=...)` — close the active session; returns truthy if a row was updated.
- `gateway/app/db.py:80` — `create_record(...)` — insert; enforces "at most one active" by no-op when one already exists.
- `gateway/app/db.py:98` — `update_record(id, **fields)` — inline UI edit path.
- `gateway/app/db.py:116` — `delete_record(id)`.
- `gateway/app/db.py:123` — `list_records(limit=..., before_epoch=...)` — newest-first pagination.
- `gateway/app/db.py:148` — `count_records()`.
- `gateway/app/config.py:9` — `DEFAULTS` — full key list with seed values (OpenClaw, scheduler, UI prefills, timezone).
- `gateway/app/config.py:76` — `load()` — returns merged-with-defaults dict from cache (lazy init from disk).
- `gateway/app/config.py:87` — `update(items)` — merges into the on-disk JSON via atomic `os.replace`, refreshes cache.
- `gateway/app/config.py:98` — `migrate_from(legacy_loader)` — seed `config.json` from the legacy SQLite `config` table on first start; no-op once the file exists. `CONFIG_PATH` env `GATEWAY_CONFIG_PATH` (default `/feeding/config.json`).

## Interactions

- Consumed on every route in [gateway-api.md](gateway-api.md).
- [gateway-openclaw.md](gateway-openclaw.md) reads `get_active`,
  writes via `stop_active` (auto-stop) and reads `list_records`
  (auto-sync bundle).

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
