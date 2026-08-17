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
| `gateway/app/util.py` | timezone resolution + the midnight-splitting time math shared with the scheduler |

## Key Types and Entry Points

- `gateway/app/main.py:34` — `filter_localtime` — UTC epoch → local timestamp string.
- `gateway/app/main.py:42` — `filter_localdate_input` — epoch → `YYYY-MM-DD` for `<input type=date>`.
- `gateway/app/main.py:48` — `filter_localtime_only` — epoch → `HH:MM` for time input.
- `gateway/app/main.py:54` — `filter_duration` — `(start, stop)` → `"Xh Ym"` (≥1 h) or `"Xm"` (sub-hour, minutes only — no seconds).
- `gateway/app/main.py:120` — `lifespan` — startup: `db.init()`, `config.migrate_from(...)`, spawn `scheduler.scheduler_loop` as a background task.
- `gateway/app/main.py` — `require_auth` — one global dependency (`FastAPI(dependencies=[...])`) gating every route, API and browser UI alike. Order: no-op when `GATEWAY_TOKEN` is unset → pass when the effective client IP is in a `trusted_networks` CIDR (default `10.0.0.0/8`) → otherwise accept `Authorization: Bearer <token>` (machines), HTTP Basic where the password is the token (browser fallback), or the derived browser-access cookie. On failure it returns `401` with `WWW-Authenticate: Basic realm="babytime"`; secret comparisons use `hmac.compare_digest`. The `/static` mount is a sub-app and stays open (CSS only).
- `gateway/app/main.py` — `browser_api_key_link` middleware — a GET to `/?api=<GATEWAY_TOKEN>` issues an HttpOnly, SameSite=Lax, Secure browser cookie valid for one year, then normally returns a no-store/no-referrer 303 with `api` removed. `&shortcut=1` is the explicit iOS Home Screen mode: it renders the page without stripping either query value, allowing the saved icon to reauthenticate a standalone cookie context on every launch. The cookie is HMAC-derived rather than the raw key; both modes require HTTPS.
- `gateway/app/main.py:139` — `_effective_client_ip` — the IP the trust check keys on. Normally `request.client.host` (the TCP peer). When that peer is in `trusted_proxies` (CIDR list, empty by default) it walks the `X-Forwarded-For` chain from the connection side inward, skipping further trusted-proxy hops, to the real client behind the reverse proxy. `X-Forwarded-For` is ignored when the peer isn't a configured proxy, so a direct client can't spoof a LAN IP. uvicorn is launched with `--no-proxy-headers` (see `Dockerfile`) so it leaves `request.client` as the real peer instead of rewriting it from forwarded headers — this module is the single authority on proxy headers.
- `gateway/app/main.py` — `_feeding_bounds(end, cfg)` derives every new feeding as `(end - auto_stop_minutes, end)`; `0` retains point-record behavior. The result runs through `_segments`, so a feed logged just after midnight is trimmed back to `23:59:59` of the day it started on instead of straddling the boundary.
- `gateway/app/util.py` — `midnight_segments(start, stop, activity, tz)` — **the midnight rule**: no stored record crosses local midnight, so every row belongs to exactly one calendar day and daily totals need no span arithmetic. Sleep (`util.SPLIT_ACTIVITIES`) splits — `19:00 → 01:00` becomes `19:00–23:59:59` plus `00:00:00–01:00` — and the one-second gap is deliberate, so day one still reads `23:59` rather than a next-day-looking `00:00`. Every other activity is clamped to `23:59:59` of the day it started on, so `23:50 → 00:05` is filed as `23:50–23:59:59` on the earlier day (those types are capped at 30 minutes, so little is trimmed). An open span (`stop` `None`) passes through and is cut when it closes. `local_midnight_after(epoch, tz)` is the boundary helper underneath.
- `gateway/app/main.py` — `_segments(start, stop, activity, cfg)` — `util.midnight_segments` bound to the configured timezone; every write path funnels through it (device events, the activity-bar toggle, both form routes, `POST`/`PATCH /api/records`, and the scheduler's auto-stop). `_create_segments(segments, **fields)` inserts one row per segment and returns the first id; `_update_segments(rid, segments, **fields)` rewrites `rid` as the first segment and spills the rest; `_stop_session(activity, stop_epoch, cfg)` closes an open session the same way (returns `False` when nothing was running, which is what makes the `/ui/activity` toggle fall through to "start"). Rows written before this rule shipped are left alone — there is no backfill.
- `gateway/app/main.py` — `state_payload` — assembles `{active, last_feeding, today_feeds, today_ml, history, server_epoch, feeding_duration_minutes, feeding_alert}` for `/api/state`. `history` is the newest eight records of every activity; `last_feeding` is the newest **completed** feeding. `today_feeds`/`today_ml` use feeding End time for the gateway-local day. The duration field synchronizes ESP32 optimistic local records with gateway configuration.
- `gateway/app/main.py` — `POST /api/events` — current firmware sends `type="log"`; `timestamp_epoch` is the feeding End, Start is the configured duration earlier, and `default_volume_ml` is applied. A `log` or legacy feeding `stop` normalizes an open feeding to those same bounds. Legacy `start`/`stop` remain accepted during device upgrades.
- `gateway/app/main.py:294` — `GET /api/state` — device polling target.
- `GET /api/records` — JSON record list (newest-first, `limit`). With `?date=YYYY-MM-DD` it instead returns a day object `{date, records, day_note, summary:{feeds, total_ml}}` via `_day_payload`: that date's records oldest-first (bucketed in the gateway tz, matching the web UI grouping), the day's note, and a feeding tally counting volume-bearing feedings. Backs the skill's `dump` command. Bad date → 400.
- `POST /api/records` — create a record from JSON (`RecordIn`); `start` is required for wire compatibility. For feeding it means End (an explicit `stop` wins), and stored Start is derived from configuration. Other timed activities retain start/stop normalization and the 30-minute guard. A sleep spanning midnight is stored as one record per calendar day; the response is the **first** row, its siblings come back from `GET /api/records`.
- `PATCH /api/records/{rid}` — partial update. Feeding time edits treat the supplied time as End and recalculate Start; changing a session to feeding does the same. Other timed records retain the 30-minute guard. Stretching a sleep past midnight splits it here too: `rid` keeps the first day and a new row holds the remainder.
- `DELETE /api/records/{rid}` — delete by id; 404 if absent.
- `GET /api/day_notes` — `{date: note}` map of all per-day notes.
- `PUT /api/day_notes/{date}` — upsert one day's note (`DayNoteIn`); `date` validated as `YYYY-MM-DD`; a blank note clears the entry. Returns `{date, note}`.
- `GET /api/config` — non-secret config dump.
- `GET /api/activities` — `[{activity, timed}, ...]` for the configured types (via `config.activity_list` + `timed_activities`); lets an agent discover what it may add and which types are start→stop vs instant.
- `_to_epoch(value, tz)` — JSON timestamp coercion (epoch int, digit string, or ISO/`Z`/offset; naive strings read in the configured tz). Shared by the write endpoints.
- `_feeding_volume(activity, raw)` — single definition of the "volume only for feeding" rule, shared by the form routes, the JSON endpoints, and the start handlers that stamp `default_volume_ml`. Returns `None` for non-feeding or a blank value, so an unset default is a no-op.
- `_normalize_stop_epoch(start_epoch, stop_epoch)` — shared record-duration guard. `None` remains open, a stop before start is treated as crossing midnight, and a duration over 30 minutes raises HTTP 400 (24 hours for sleep). It only sizes the span; `_segments` afterwards decides how it is stored across a day boundary.
- `gateway/app/main.py` — `ui_home` (`GET /`) — groups feedings by local End date and other records by Start date, then paginates by date count (`ui_show_count`).
- `POST /ui/activity` — feeding normally opens the browser dialog; a direct feeding post uses now as End, configured duration for Start, and configured default volume. Other timed activities still toggle and other point activities log immediately.
- `gateway/app/main.py` — `POST /records` (`ui_create`) — the feeding dialog submits one End that defaults to now; the route derives Start, stamps `device_id="web"`, and ignores a legacy submitted feeding Start. Older non-feeding start/end callers remain accepted.
- `POST /records/save` — inline edit of checked rows plus day notes. Feeding Start is read-only in the table and recalculated whenever End is edited. Non-feeding point rows keep equal timestamps; other timed sessions retain start/end duration validation.
- `POST /records/delete` — deletes the checked rows.
- `POST /config` — saves the config form. The handler rebuilds `activity_types` and `timed_activities` from the per-row controls. Feeding is read-only and its timed control is disabled because it always uses an end time.

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
  `today_feeds`, `today_ml`, `history`, `server_epoch`,
  `feeding_duration_minutes`, and `feeding_alert` keys.
- Pass = second `curl` prints at least one line containing
  `activity-bar` (HTML rendered with the activity-button bar).
Midnight rule (replace the dates with any two consecutive days):

```sh
curl -s -X POST http://localhost:8080/api/records -H 'Content-Type: application/json' \
  -d '{"activity":"sleep","start":"2026-08-17 19:00","stop":"2026-08-18 01:00"}'
curl -s -X POST http://localhost:8080/api/records -H 'Content-Type: application/json' \
  -d '{"activity":"feeding","start":"2026-08-19 00:05","volume_ml":120}'
curl -s 'http://localhost:8080/api/records?date=2026-08-17' | jq '.summary.sleep_duration'
```

- Pass = the sleep POST returns a record ending `23:59:59` on 08-17 and
  `GET /api/records?date=2026-08-18` shows its `00:00:00–01:00` sibling.
- Pass = the feeding lands on 08-18 as `23:50:00–23:59:59`, not 08-19.
- Pass = the day summary prints `"04:59"`.

- With a non-empty `GATEWAY_TOKEN` and an untrusted client, `GET /` returns
  401. `GET /?api=<token>` over HTTPS returns a 303 with an HttpOnly/Secure
  cookie and a clean `Location: /`; following that redirect with the cookie
  renders the UI. A wrong key still returns 401, while Bearer auth continues
  to work for API clients. Adding `&shortcut=1` returns the UI directly with
  status 200, preserves the query, and sets the same protected cookie.

## Open Gaps / Roadmap

- Editing an already-split sleep so that it crosses midnight *again*
  produces a fresh day-two row without removing the earlier one — the two
  halves are independent records with nothing linking them. Fixing it
  properly needs a parent/segment id on `records`.
- A record clamped to `23:59:59` renders as `23:59` in the inline editor;
  re-saving that row unchanged rewrites it as `23:59:00`, shaving 59
  seconds. Harmless for `HH:MM` totals.
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
