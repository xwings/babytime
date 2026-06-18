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
- **Browsers** outside the trusted range get an HTTP Basic prompt; enter the
  token as the password (the username is ignored).

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

- `POST /api/events` — `{type: "start"|"stop", device_id, timestamp_epoch?}`
  starts a session (no-op if one is already active) or stops the active one.
  Returns the new state payload.
- `GET /api/state` — returns `{active, last_feeding, today_feeds, today_ml,
  history (last 8), server_epoch, feeding_alert}`.

Agent-facing:

- `GET /api/records` / `POST /api/records` — list (newest-first) and create.
  A supplied stop time must be within 30 minutes of the start time.
- `PATCH /api/records/{id}` / `DELETE /api/records/{id}` — edit / remove.
  Edits that leave a record longer than 30 minutes are rejected.
- `GET /api/day_notes` — `{date: note}` map of all per-day notes.
- `PUT /api/day_notes/{date}` — `{note: "..."}` upserts one day's note
  (blank note clears it). `date` must be `YYYY-MM-DD`.
- `GET /api/config` — non-secret config dump.

UI/admin:

- `GET /` — web UI: records table with inline edit, add-record form, per-date
  day-note field, configuration form.
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
| `feeding_alert_minutes` | `120` | after the last completed feeding is this many minutes old, `/api/state` reports `feeding_alert.due=true`, the web activity buttons blink blue/red, and the device display blinks a red background. `0` disables |
| `default_volume_ml` | `` | pre-fills the ml field of the Add-record form |
| `default_language` | `en` | UI language (`en`/`zh`) for browsers without a `lang` cookie; the per-browser switch still overrides it |
| `timezone` | `UTC` | IANA name, e.g. `Asia/Shanghai` |
| `ui_show_count` | `10` | dates per page on the web UI (records grouped by date; rows from the last 24h are pre-checked) |
| `trusted_networks` | `10.0.0.0/8` | comma-separated CIDR blocks whose clients skip auth when `GATEWAY_TOKEN` is set; everyone else must present the token. Unparseable entries are ignored |
| `trusted_proxies` | `` | comma-separated CIDR blocks of reverse proxies whose `X-Forwarded-For` is believed; empty means the header is ignored. Set this to your proxy's source IP so the real client IP drives the trust/auth decision |
