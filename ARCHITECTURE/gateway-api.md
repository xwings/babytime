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

- `gateway/app/main.py:34` — `filter_localtime` — UTC epoch → local timestamp string.
- `gateway/app/main.py:42` — `filter_localdate_input` — epoch → `YYYY-MM-DD` for `<input type=date>`.
- `gateway/app/main.py:48` — `filter_localtime_only` — epoch → `HH:MM` for time input.
- `gateway/app/main.py:54` — `filter_duration` — `(start, stop)` → `"Xh Ym"` (≥1 h) or `"Xm"` (sub-hour, minutes only — no seconds).
- `gateway/app/main.py:120` — `lifespan` — startup: `db.init()`, `config.migrate_from(...)`, spawn `scheduler.scheduler_loop` as a background task.
- `gateway/app/main.py:196` — `require_auth` — one global dependency (`FastAPI(dependencies=[...])`) gating every route, API and browser UI alike. Order: no-op when `GATEWAY_TOKEN` is unset → pass when the effective client IP is in a `trusted_networks` CIDR (default `10.0.0.0/8`) → otherwise the request must carry the token, as `Authorization: Bearer <token>` (machines) or HTTP Basic where the password is the token (browsers; username ignored). On failure it returns `401` with `WWW-Authenticate: Basic realm="babytime"` so browsers pop the native login; the token compare uses `hmac.compare_digest`. The `/static` mount is a sub-app and stays open (CSS only).
- `gateway/app/main.py:139` — `_effective_client_ip` — the IP the trust check keys on. Normally `request.client.host` (the TCP peer). When that peer is in `trusted_proxies` (CIDR list, empty by default) it walks the `X-Forwarded-For` chain from the connection side inward, skipping further trusted-proxy hops, to the real client behind the reverse proxy. `X-Forwarded-For` is ignored when the peer isn't a configured proxy, so a direct client can't spoof a LAN IP. uvicorn is launched with `--no-proxy-headers` (see `Dockerfile`) so it leaves `request.client` as the real peer instead of rewriting it from forwarded headers — this module is the single authority on proxy headers.
- `gateway/app/main.py:242` — `state_payload` — assembles `{active, last_feeding, today_feeds, today_ml, history, server_epoch, feeding_alert}` for `/api/state`. `history` is `db.list_records(limit=8)` — **all** activity types, so the device's activity screen can list everything. The feeding-specific fields keep the live counter accurate regardless of what tops the history: `active` is `db.get_active("feeding")` (open feeding session) and `last_feeding` is `db.list_records(limit=1, activity="feeding")[0]` (most recent feeding) — so a newer sleep/poopoo never masquerades as the active session or the "last fed" time. `today_feeds`/`today_ml` come from `db.feeding_totals` over the local-midnight-to-midnight window (gateway timezone) and feed the counter screen's daily tally; the count pairs with ml (feedings carrying a volume only). `feeding_alert` is due when there is no active feeding and the last completed feeding is at least `feeding_alert_minutes` old.
- `gateway/app/main.py:275` — `POST /api/events` — start/stop toggle; honors `timestamp_epoch` override. A feeding `start` stamps the configured `default_volume_ml` on the new record (via `_feeding_volume`), so a feed logged from the device button isn't left blank; a blank/unset default stays `NULL`, and non-feeding starts never carry volume.
- `gateway/app/main.py:294` — `GET /api/state` — device polling target.
- `GET /api/records` — JSON record list (newest-first, `limit`). With `?date=YYYY-MM-DD` it instead returns a day object `{date, records, day_note, summary:{feeds, total_ml}}` via `_day_payload`: that date's records oldest-first (bucketed in the gateway tz, matching the web UI grouping), the day's note, and a feeding tally counting volume-bearing feedings. Backs the skill's `dump` command. Bad date → 400.
- `POST /api/records` — create a record from JSON (`RecordIn`); `start` required, `activity` defaults to `feeding`, `volume_ml` kept only for feeding. A supplied `stop` is normalized across midnight and rejected with 400 when it is more than 30 minutes after `start`. Returns the stored row.
- `PATCH /api/records/{rid}` — partial update (only fields present in the body change; uses pydantic `exclude_unset`); re-applies the feeding-only-ml rule and the 30-minute max duration rule; 404 if absent.
- `DELETE /api/records/{rid}` — delete by id; 404 if absent.
- `GET /api/day_notes` — `{date: note}` map of all per-day notes.
- `PUT /api/day_notes/{date}` — upsert one day's note (`DayNoteIn`); `date` validated as `YYYY-MM-DD`; a blank note clears the entry. Returns `{date, note}`.
- `GET /api/config` — non-secret config dump.
- `GET /api/activities` — `[{activity, timed}, ...]` for the configured types (via `config.activity_list` + `timed_activities`); lets an agent discover what it may add and which types are start→stop vs instant.
- `_to_epoch(value, tz)` — JSON timestamp coercion (epoch int, digit string, or ISO/`Z`/offset; naive strings read in the configured tz). Shared by the write endpoints.
- `_feeding_volume(activity, raw)` — single definition of the "volume only for feeding" rule, shared by the form routes, the JSON endpoints, and the start handlers that stamp `default_volume_ml`. Returns `None` for non-feeding or a blank value, so an unset default is a no-op.
- `_normalize_stop_epoch(start_epoch, stop_epoch)` — shared record-duration guard. `None` remains open, a stop before start is treated as crossing midnight, and a duration over 30 minutes raises HTTP 400.
- `gateway/app/main.py:447` — `ui_home` (`GET /`) — groups records by local date, paginates by date count (`ui_show_count`).
- `POST /ui/activity` — web-initiated tap for a chosen activity; stamps `device_id="web"`. Timed activities (`config.timed_activities`) toggle start↔stop; instant activities log one closed record (`stop_epoch == start_epoch`) so they never open a session. Like `/api/events`, a feeding start stamps `default_volume_ml` so the web feed-now button and the device button behave the same.
- `gateway/app/main.py:574` — `POST /records` (`ui_create`) — add via form; the form's `activity` `<select>` lets any configured activity be logged manually. Instant activities are stored closed (`stop_epoch = start_epoch`); timed ones keep the submitted stop (with the next-day wrap when stop < start) only when the duration is 30 minutes or less.
- `POST /records/save` — inline edit of the checked rows (including each row's `notes_<id>` free-text note; blank clears it); rows for an instant activity are re-closed (`stop_epoch = start_epoch`) since their stop is not editable. Timed rows over 30 minutes are rejected. Also persists each `day_note_<date>` field via `db.set_day_note`, so one Save writes both records and day notes.
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

- Pass = first `curl` prints a JSON object with `active`, `last_feeding`,
  `today_feeds`, `today_ml`, `history`, `server_epoch`, and `feeding_alert`
  keys.
- Pass = second `curl` prints at least one line containing
  `activity-bar` (HTML rendered with the activity-button bar).

## Open Gaps / Roadmap

- Record and day-note mutation have JSON APIs
  (`POST/PATCH/DELETE /api/records`, `PUT /api/day_notes/{date}`),
  consumed by the `skill/` agent client; the old form routes
  (`/records*`) remain for the web UI only.
- Behind a reverse proxy, `trusted_proxies` must list the proxy's
  source IP (as seen by the gateway) for `X-Forwarded-For` to be
  honoured; otherwise the proxy itself is the effective client and a
  proxy inside `trusted_networks` would make every forwarded request
  look trusted. Only `X-Forwarded-For` is read (not `Forwarded` /
  `X-Real-IP`).
- No per-route metrics, structured logging, or rate limiting.
