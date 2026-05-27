# Babytime Feeding Gateway

Tiny FastAPI + SQLite service that lets multiple ESP32 baby-feeding trackers
share one durable activity log, edited from a web UI or driven by a remote
agent over a JSON API.

## Run

```sh
docker compose up -d --build
```

Then open http://localhost:8080/ — records, manual edit, per-day notes, and
configuration all live on one page.

Persisted in `./babytime/` on the host (mounted to `/babytime` in the container):

- `gateway.db` — SQLite, holds activity records and per-day notes.
- `config.json` — auto-stop cap, UI prefills, activity types, timezone, UI
  options. Editable from the web UI **or** by hand; written atomically. Keys
  match those in the Config section below.

Change the host path or host port in `docker-compose.yml` if you need different
bindings. If you're upgrading from a build that stored config in SQLite, the
gateway copies the old `config` table into `config.json` on first start.

Remote agents read and edit records over the JSON API
(`GET/POST /api/records`, `PATCH/DELETE /api/records/{id}`) and write per-day
notes (`GET /api/day_notes`, `PUT /api/day_notes/{date}`). The `skill/` folder
at the repo root packages this for a third-party agent — install it and point
`BABYTIME_GATEWAY_URL` / `BABYTIME_GATEWAY_TOKEN` at this gateway.

## Auth

By default, set `GATEWAY_TOKEN` to `""` in `docker-compose.yml` (LAN-trust, no
auth). Set a non-empty token to require `Authorization: Bearer <token>` on all
`/api/*` endpoints (and the same token in firmware `config.local.h`).

## API

Device-facing:

- `POST /api/events` — `{type: "start"|"stop", device_id, timestamp_epoch?}`
  starts a session (no-op if one is already active) or stops the active one.
  Returns the new state payload.
- `GET /api/state` — returns `{active, history (last 8), server_epoch}`.

Agent-facing:

- `GET /api/records` / `POST /api/records` — list (newest-first) and create.
- `PATCH /api/records/{id}` / `DELETE /api/records/{id}` — edit / remove.
- `GET /api/day_notes` — `{date: note}` map of all per-day notes.
- `PUT /api/day_notes/{date}` — `{note: "..."}` upserts one day's note
  (blank note clears it). `date` must be `YYYY-MM-DD`.
- `GET /api/config` — non-secret config dump.

UI/admin:

- `GET /` — web UI: records table with inline edit, add-record form, per-date
  day-note field, configuration form.
- `POST /records`, `POST /records/save`, `POST /records/delete` — form
  actions. `POST /records/save` persists both record edits and day notes.
- `POST /config` — saves the form.

## Day notes

Each calendar date can carry one free-text note. Edit it inline in the date
group's header on the web UI and click **Save**, or write it over the JSON API
(`PUT /api/day_notes/{date}`) — that's the path a remote agent uses to record
a daily summary.

## Auto-stop

`auto_stop_minutes` caps any active session: a background loop checks once a
minute and stops a session that has run longer than the cap (default 15;
`0` disables). Guards against a device that started a session and dropped off
the network without sending `stop`.

## Config keys

| Key | Default | Notes |
| --- | --- | --- |
| `activity_types` | `feeding,sleep,poopoo` | comma-separated; `feeding` always first |
| `timed_activities` | `feeding,sleep` | comma-separated subset of `activity_types` that record as start→stop sessions with a timer; the rest log a single instant timestamp. `feeding` is always timed |
| `auto_stop_minutes` | `15` | auto-stop an active session after this many minutes (0 disables) |
| `default_volume_ml` | `` | pre-fills the ml field of the Add-record form |
| `default_language` | `en` | UI language (`en`/`zh`) for browsers without a `lang` cookie; the per-browser switch still overrides it |
| `timezone` | `UTC` | IANA name, e.g. `Asia/Shanghai` |
| `ui_show_count` | `10` | dates per page on the web UI (records grouped by date; rows from the last 24h are pre-checked) |
