# gateway-api

## Goal

HTTP surface for the gateway. Exposes the device-facing JSON API
(`/api/events`, `/api/state`, `/api/config`) that ESP32 firmware
drives; a JSON record + day-note API (`GET/POST /api/records`,
`PATCH/DELETE /api/records/{id}`, `GET /api/day_notes`,
`PUT /api/day_notes/{date}`) that remote agents use to read and mutate
the log (see `skill/`); plus the browser-facing routes (`/`,
`/ui/activity`, `/records*`, `/config`) that render and mutate the same
store through the web UI.

## Status

`done`.

## Code Structure

| File | Role |
| ---- | ---- |
| `gateway/app/main.py` | FastAPI app: lifespan, Jinja filters, auth dependency, all routes |

## Key Types and Entry Points

- `gateway/app/main.py:31` — `filter_localtime` — UTC epoch → local timestamp string.
- `gateway/app/main.py:39` — `filter_localdate_input` — epoch → `YYYY-MM-DD` for `<input type=date>`.
- `gateway/app/main.py:45` — `filter_localtime_only` — epoch → `HH:MM` for time input.
- `gateway/app/main.py:51` — `filter_duration` — `(start, stop)` → `"Xh Ym"` / `"Xm Ys"`.
- `gateway/app/main.py:81` — `lifespan` — startup: `db.init()`, `config.migrate_from(...)`, spawn `scheduler.scheduler_loop` as a background task.
- `gateway/app/main.py:99` — `check_token` — `Authorization: Bearer <token>` dependency, no-op when `GATEWAY_TOKEN` is unset.
- `gateway/app/main.py:109` — `state_payload` — assembles `{active, history, server_epoch}` for `/api/state`; `active` is `db.get_active("feeding")` (the device is feeding-centric, so an open sleep/instant record never masquerades as the device's active session).
- `gateway/app/main.py:128` — `POST /api/events` — start/stop toggle; honors `timestamp_epoch` override.
- `gateway/app/main.py:142` — `GET /api/state` — device polling target.
- `GET /api/records` — JSON record list (newest-first, `limit`).
- `POST /api/records` — create a record from JSON (`RecordIn`); `start` required, `activity` defaults to `feeding`, `volume_ml` kept only for feeding. Returns the stored row.
- `PATCH /api/records/{rid}` — partial update (only fields present in the body change; uses pydantic `exclude_unset`); re-applies the feeding-only-ml rule; 404 if absent.
- `DELETE /api/records/{rid}` — delete by id; 404 if absent.
- `GET /api/day_notes` — `{date: note}` map of all per-day notes.
- `PUT /api/day_notes/{date}` — upsert one day's note (`DayNoteIn`); `date` validated as `YYYY-MM-DD`; a blank note clears the entry. Returns `{date, note}`.
- `GET /api/config` — non-secret config dump.
- `_to_epoch(value, tz)` — JSON timestamp coercion (epoch int, digit string, or ISO/`Z`/offset; naive strings read in the configured tz). Shared by the write endpoints.
- `_feeding_volume(activity, raw)` — single definition of the "volume only for feeding" rule, shared by the form routes and the JSON endpoints.
- `gateway/app/main.py:174` — `ui_home` (`GET /`) — groups records by local date, paginates by date count (`ui_show_count`).
- `POST /ui/activity` — web-initiated tap for a chosen activity; stamps `device_id="web"`. Timed activities (`config.timed_activities`) toggle start↔stop; instant activities log one closed record (`stop_epoch == start_epoch`) so they never open a session.
- `gateway/app/main.py:272` — `POST /records` — add via form.
- `POST /records/save` — inline edit of the checked rows; rows for an instant activity are re-closed (`stop_epoch = start_epoch`) since their stop is not editable. Also persists each `day_note_<date>` field via `db.set_day_note`, so one Save writes both records and day notes.
- `POST /records/delete` — deletes the checked rows.
- `POST /config` — saves the config form. The per-activity rows arrive as `activity_name_<i>` inputs plus optional `activity_timed_<i>` checkboxes; the handler rebuilds `activity_types` (names in form order) and `timed_activities` (names whose checkbox was on) from them, and passes every other field through unchanged. `config.activity_list`/`timed_activities` re-force `feeding`, so the read-only/disabled feeding row need not round-trip.

## Interactions

- Reads/writes through [gateway-storage.md](gateway-storage.md) for
  records, day notes, and config on every route.
- `lifespan` launches the auto-stop loop from
  [gateway-scheduler.md](gateway-scheduler.md) via
  `asyncio.create_task(scheduler.scheduler_loop())`.
- Renders templates owned by [gateway-ui.md](gateway-ui.md).

## How to Test

From `gateway/`:

```sh
docker compose up -d --build
curl -s http://localhost:8080/api/state | jq .
curl -s http://localhost:8080/ | grep -F 'activity-bar'
```

- Pass = first `curl` prints a JSON object with `active`, `history`,
  and `server_epoch` keys.
- Pass = second `curl` prints at least one line containing
  `activity-bar` (HTML rendered with the activity-button bar).

## Open Gaps / Roadmap

- Record and day-note mutation have JSON APIs
  (`POST/PATCH/DELETE /api/records`, `PUT /api/day_notes/{date}`),
  consumed by the `skill/` agent client; the old form routes
  (`/records*`) remain for the web UI only.
- `/ui/*` and `/records*` routes are not behind `check_token`;
  LAN-trust is assumed. Could move under the same dependency when
  `GATEWAY_TOKEN` is set, but no work tracked yet.
- No per-route metrics, structured logging, or rate limiting.
