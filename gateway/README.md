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
- `config.json` — auto-stop cap, feed-due alert threshold, UI prefills,
  activity types, timezone, UI options. Editable from the web UI **or** by
  hand; written atomically. Keys match those in the Config section below.

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
auth). Set a non-empty token to require it on **every** route — the JSON API
and the browser UI.

Clients on a trusted network skip auth entirely (the gateway is meant to be
open on the home LAN); the `trusted_networks` config key lists the CIDR blocks,
default `10.0.0.0/8`. Everyone else must present the token:

- **Machines** (firmware, the `skill/` client) send `Authorization: Bearer
  <token>` — put the same token in firmware `config.local.h`.
- **Browsers** can use a one-click API-key link:
  `https://baby.example.com/?api=<token>`. A valid link sets a one-year,
  HttpOnly browser cookie and immediately redirects to `/`, removing the key
  from the visible address. The cookie contains a derived credential rather
  than the raw token; changing `GATEWAY_TOKEN` invalidates it. The cookie is
  Secure, so the public link must use HTTPS.
- **iOS Home Screen shortcuts** should use
  `https://baby.example.com/?api=<token>&shortcut=1`. Shortcut mode keeps the
  key in the URL instead of redirecting, so Add to Home Screen saves it and
  each standalone launch can recreate its cookie. The page applies
  `Referrer-Policy: no-referrer` and `Cache-Control: no-store`, but the key is
  still visible in the shortcut and server/proxy access logs.
- HTTP Basic remains available as a fallback: enter the token as the password
  (the username is ignored).

Treat the complete API-key link like a password and share it only with people
who should be able to view and edit the baby log. The initial URL may still be
recorded in browser, reverse-proxy, or hosting access logs. Use a long random
token (for example, `openssl rand -hex 32`) and HTTPS.

### Behind a reverse proxy

The gateway keys trust on the connecting IP, which behind a proxy (nginx,
etc.) is the *proxy's* IP — and if that IP sits inside `trusted_networks`
(e.g. a LAN nginx in `10.0.0.0/8`), every forwarded request would look
trusted and skip auth. To fix this, list the proxy's source IP (as the
gateway sees it) in `trusted_proxies`; the gateway then reads the real client
from the proxy's `X-Forwarded-For` header and applies the trust/auth rules to
*that*. The header is ignored unless the peer is a configured proxy, so it
can't be spoofed.

Make the proxy forward the header (nginx: `proxy_set_header X-Forwarded-For
$proxy_add_x_forwarded_for;`). If unsure which source IP to trust, hit the
gateway through the proxy with a token set and check the container logs — the
`401` line shows the peer IP uvicorn saw.

## API

Device-facing:

- `POST /api/events` — `{type: "log", device_id, timestamp_epoch?}` logs a
  completed feeding whose end time is `timestamp_epoch` (or now) and applies
  `default_volume_ml`. Start is End minus `auto_stop_minutes`; an older open
  feeding is normalized to the same duration by `log` or `stop`. Legacy events
  remain accepted during upgrades. Returns the new state payload.
- `GET /api/state` — returns `{active, last_feeding, today_feeds, today_ml,
  history (last 8), server_epoch, feeding_duration_minutes, feeding_alert}`.

Agent-facing:

- `GET /api/records` / `POST /api/records` — list (newest-first) and create.
  For feeding, `start` is interpreted as the end time (or an explicit `stop`
  wins); the stored Start is recalculated from the configured duration. Other
  timed activities keep their start/stop bounds; a supplied stop must be
  within 30 minutes of start.
- `PATCH /api/records/{id}` / `DELETE /api/records/{id}` — edit / remove.
  Edits that leave a record longer than 30 minutes are rejected.
- `GET /api/day_notes` — `{date: note}` map of all per-day notes.
- `PUT /api/day_notes/{date}` — `{note: "..."}` upserts one day's note
  (blank note clears it). `date` must be `YYYY-MM-DD`.
- `GET /api/config` — non-secret config dump.

UI/admin:

- `GET /` — web UI: records table with inline edit, a phone-sized Add-record
  dialog with compact −/milk/+ controls and one End field, per-date day-note
  field, and configuration form. End refreshes to the current gateway time
  whenever the dialog opens; Start is calculated on save. Feeding rows are
  grouped by End date and expose Start as read-only.
- `POST /records`, `POST /records/save`, `POST /records/delete` — form
  actions. Timed records must stop within 30 minutes of their start.
  `POST /records/save` persists both record edits and day notes.
- `POST /config` — saves the form.

## Day notes

Each calendar date can carry one free-text note. Edit it inline in the date
group's header on the web UI and click **Save**, or write it over the JSON API
(`PUT /api/day_notes/{date}`) — that's the path a remote agent uses to record
a daily summary.

## Auto-stop

`auto_stop_minutes` is the shared feeding duration and active-session cap. A
web or ESP32 feeding gets `Start = End - auto_stop_minutes`. The background
loop also checks once a minute and stops an active session that has run longer
than that cap (default 15; `0` disables the cap and produces point feedings).

## Config keys

| Key | Default | Notes |
| --- | --- | --- |
| `activity_types` | `feeding,sleep,poopoo` | comma-separated; `feeding` always first |
| `timed_activities` | `sleep` | comma-separated subset controlling activity-bar timers. Feeding is handled separately by its end-time milk dialog (and by one end-time press on ESP32), so legacy `feeding` entries here are ignored |
| `auto_stop_minutes` | `15` | feeding duration (`Start = End - minutes`) and auto-stop cap for active sessions; `0` produces point feedings and disables auto-stop |
| `feeding_alert_minutes` | `120` | after the last completed feeding is this many minutes old, `/api/state` reports `feeding_alert.due=true`, the web Feeding button blinks blue/red, and the device display blinks a red background. `0` disables |
| `default_volume_ml` | `` | pre-fills the web milk dialog and is attached to a feeding logged from an ESP32 button |
| `default_language` | `en` | UI language (`en`/`zh`) for browsers without a `lang` cookie; the per-browser switch still overrides it |
| `timezone` | `UTC` | IANA name, e.g. `Asia/Shanghai` |
| `ui_show_count` | `10` | dates per page on the web UI (records grouped by date; rows from the last 24h are pre-checked) |
| `trusted_networks` | `10.0.0.0/8` | comma-separated CIDR blocks whose clients skip auth when `GATEWAY_TOKEN` is set; everyone else must present the token. Unparseable entries are ignored |
| `trusted_proxies` | `` | comma-separated CIDR blocks of reverse proxies whose `X-Forwarded-For` is believed; empty means the header is ignored. Set this to your proxy's source IP so the real client IP drives the trust/auth decision |
