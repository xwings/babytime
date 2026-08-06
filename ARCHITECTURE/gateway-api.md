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
- `gateway/app/main.py` — `require_auth` — one global dependency (`FastAPI(dependencies=[...])`) gating every route, API and browser UI alike. Order: no-op when `GATEWAY_TOKEN` is unset → pass when the effective client IP is in a `trusted_networks` CIDR (default `10.0.0.0/8`) → otherwise accept `Authorization: Bearer <token>` (machines), HTTP Basic where the password is the token (browser fallback), or the derived browser-access cookie. On failure it returns `401` with `WWW-Authenticate: Basic realm="babytime"`; secret comparisons use `hmac.compare_digest`. The `/static` mount is a sub-app and stays open (CSS only).
- `gateway/app/main.py` — `browser_api_key_link` middleware — a GET to `/?api=<GATEWAY_TOKEN>` issues an HttpOnly, SameSite=Lax, Secure browser cookie valid for one year, then normally returns a no-store/no-referrer 303 with `api` removed. `&shortcut=1` is the explicit iOS Home Screen mode: it renders the page without stripping either query value, allowing the saved icon to reauthenticate a standalone cookie context on every launch. The cookie is HMAC-derived rather than the raw key; both modes require HTTPS.
- `gateway/app/main.py:139` — `_effective_client_ip` — the IP the trust check keys on. Normally `request.client.host` (the TCP peer). When that peer is in `trusted_proxies` (CIDR list, empty by default) it walks the `X-Forwarded-For` chain from the connection side inward, skipping further trusted-proxy hops, to the real client behind the reverse proxy. `X-Forwarded-For` is ignored when the peer isn't a configured proxy, so a direct client can't spoof a LAN IP. uvicorn is launched with `--no-proxy-headers` (see `Dockerfile`) so it leaves `request.client` as the real peer instead of rewriting it from forwarded headers — this module is the single authority on proxy headers.
- `gateway/app/main.py` — `_feeding_bounds(end, cfg)` derives every new feeding as `(end - auto_stop_minutes, end)`; `0` retains point-record behavior.
- `gateway/app/main.py` — `state_payload` — assembles `{active, last_feeding, today_feeds, today_ml, history, server_epoch, feeding_duration_minutes, feeding_alert}` for `/api/state`. `history` is the newest eight records of every activity; `last_feeding` is the newest **completed** feeding. `today_feeds`/`today_ml` use feeding End time for the gateway-local day. The duration field synchronizes ESP32 optimistic local records with gateway configuration.
- `gateway/app/main.py` — `POST /api/events` — current firmware sends `type="log"`; `timestamp_epoch` is the feeding End, Start is the configured duration earlier, and `default_volume_ml` is applied. A `log` or legacy feeding `stop` normalizes an open feeding to those same bounds. Legacy `start`/`stop` remain accepted during device upgrades.
- `gateway/app/main.py:294` — `GET /api/state` — device polling target.
- `GET /api/records` — JSON record list (newest-first, `limit`). With `?date=YYYY-MM-DD` it instead returns a day object `{date, records, day_note, summary:{feeds, total_ml}}` via `_day_payload`: that date's records oldest-first (bucketed in the gateway tz, matching the web UI grouping), the day's note, and a feeding tally counting volume-bearing feedings. Backs the skill's `dump` command. Bad date → 400.
- `POST /api/records` — create a record from JSON (`RecordIn`); `start` is required for wire compatibility. For feeding it means End (an explicit `stop` wins), and stored Start is derived from configuration. Other timed activities retain start/stop normalization and the 30-minute guard.
- `PATCH /api/records/{rid}` — partial update. Feeding time edits treat the supplied time as End and recalculate Start; changing a session to feeding does the same. Other timed records retain the 30-minute guard.
- `DELETE /api/records/{rid}` — delete by id; 404 if absent.
- `GET /api/day_notes` — `{date: note}` map of all per-day notes.
- `PUT /api/day_notes/{date}` — upsert one day's note (`DayNoteIn`); `date` validated as `YYYY-MM-DD`; a blank note clears the entry. Returns `{date, note}`.
- `GET /api/config` — non-secret config dump.
- `GET /api/activities` — `[{activity, timed}, ...]` for the configured types (via `config.activity_list` + `timed_activities`); lets an agent discover what it may add and which types are start→stop vs instant.
- `_to_epoch(value, tz)` — JSON timestamp coercion (epoch int, digit string, or ISO/`Z`/offset; naive strings read in the configured tz). Shared by the write endpoints.
- `_feeding_volume(activity, raw)` — single definition of the "volume only for feeding" rule, shared by the form routes, the JSON endpoints, and the start handlers that stamp `default_volume_ml`. Returns `None` for non-feeding or a blank value, so an unset default is a no-op.
- `_normalize_stop_epoch(start_epoch, stop_epoch)` — shared record-duration guard. `None` remains open, a stop before start is treated as crossing midnight, and a duration over 30 minutes raises HTTP 400.
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
- With a non-empty `GATEWAY_TOKEN` and an untrusted client, `GET /` returns
  401. `GET /?api=<token>` over HTTPS returns a 303 with an HttpOnly/Secure
  cookie and a clean `Location: /`; following that redirect with the cookie
  renders the UI. A wrong key still returns 401, while Bearer auth continues
  to work for API clients. Adding `&shortcut=1` returns the UI directly with
  status 200, preserves the query, and sets the same protected cookie.

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
