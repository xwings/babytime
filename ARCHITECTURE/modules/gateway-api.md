---
eatmycode_version: "2.0.0"
---
# Gateway API

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `gateway/app/main.py`, `gateway/app/util.py`, gateway runtime manifests, `skill/`, HTTP contracts, authentication or timestamps.

## Responsibility and Status

Implemented gateway transport/application boundary; status **in progress**
for complete behavioral/security coverage. Owns device state/events, record
and day-note JSON, browser form handlers, template context and the stdlib
HTTP CLI. It delegates persistence, scheduling and presentation to partners.

## Code Map

| Path / symbol | Role |
| --- | --- |
| `gateway/app/main.py`: `require_auth`, `state_payload`, `ui_home`, `RecordIn` | Auth boundary, device snapshot, browser context and record input model; route decorators locate endpoints. |
| `gateway/app/util.py`: `midnight_segments` | Local-day segmentation shared with scheduler; timezone fallback. |
| `gateway/{requirements.txt,Dockerfile,docker-compose.yml}` | Runtime dependency pins, uvicorn entrypoint, environment/persistence contract. |
| `skill/{SKILL.md,scripts/babytime.py}` | Remote-client instructions and stdlib argparse/urllib adapter; no direct SQLite access. |

## Local Conventions

Follow [root conventions](../../ARCHITECTURE.md#code-conventions). Observed:
async route functions call synchronous storage helpers; Pydantic models
validate JSON shape; `HTTPException` reports client errors; forms redirect
303 after writes. Config parsing, amount normalization and midnight helpers
are shared across browser/device/JSON paths. These paths are not identical:
retain legacy field compatibility explicitly rather than assuming parity.

## Contracts and Invariants

- `lifespan` initializes SQLite, migrates absent JSON config, starts one
  scheduler task and cancels/awaits it on shutdown. Paths/token are read
  from environment; bind defaults are in Dockerfile. `TZ` is not the saved
  gateway calendar setting: `config.timezone` controls that.
- Empty `GATEWAY_TOKEN` opens application routes. With a token, trusted
  client CIDRs bypass auth; otherwise Bearer, Basic password or derived
  `babytime_access` cookie passes. Comparisons use HMAC-safe comparison.
  Static assets and FastAPI's generated documentation are outside the
  ordinary application-route dependency.
- `_effective_client_ip` walks `X-Forwarded-For` from the connection inward,
  skipping configured trusted proxies. Preserve `--no-proxy-headers` so
  uvicorn leaves the real TCP peer intact. A direct untrusted IP cannot
  normally override itself with a forwarded header; invalid hops are skipped.
- `GET /?api=...` exchanges a valid token for a year-long HttpOnly,
  SameSite=Lax, Secure HMAC-derived cookie and strips the key via 303.
  `shortcut=1` intentionally retains the key in the rendered URL. Responses
  set no-store/no-referrer. Secure cookie persistence needs HTTPS; the
  middleware itself does **not** reject HTTP key-link requests.
- JSON timestamps accept epoch or ISO strings; naive strings use saved
  gateway timezone (`_to_epoch`). Unknown timezones fall back to UTC.
  Milk (`feeding`) and `solid_food` record writes interpret `start` as End
  for compatibility, with explicit `stop` winning; stored Start derives
  from `auto_stop_minutes`. Poopoo/Supplement record writes use equal bounds.
  Intake columns are type-specific (`volume_ml` versus `volume_g`).
- Normalized explicit spans cap at 30 minutes, except sleep at 24 hours;
  earlier stop is interpreted as next day. Browser sleep accepts positive
  `HH:MM` duration up to 23:59; Etc accepts Start/End. Fixed-duration intake
  and device start/stop paths do not all apply the same duration guard.
- Closed spans pass through `midnight_segments`: sleep becomes separate
  rows ending at 23:59:59 and starting at 00:00; other types clamp to the
  start day. One boundary second is excluded. Open spans pass unchanged
  until closed; existing rows are not backfilled. Create returns the first
  segment; siblings are independent and carry no duplicate intake amount.
- Device `log` records a feeding End, normalizing a legacy open feeding;
  legacy `start`/`stop` remain accepted. `/api/state` contains feeding-only
  active/last-feeding, today's feeding tally, eight mixed-activity history
  rows, server epoch, configured duration and feeding-alert information.
- `/api/records?date=YYYY-MM-DD` returns oldest-first records, day note and
  milk/food/poopoo/sleep totals; no date returns newest-first limited rows.
  `_record_date_epoch` groups completed Milk/Food/Sleep/Poopoo/Supplement by End, others
  by Start. `ui_home` paginates dates, not records. Missing IDs return 404;
  malformed date/string timestamps are rejected. Empty day note deletes it.
- CLI uses global `--host`/`--token` flags before subcommands, Bearer auth,
  15-second request timeout and nonzero exits on HTTP/network errors.
  `update` forwards only supplied flags. `list --activity` filters after
  server limiting, so it may return fewer matching rows than the limit.

## Dependencies and Boundaries

Read [Storage](gateway-storage.md) for schema/settings changes,
[Scheduler](gateway-scheduler.md) for lifespan/cap changes,
[UI](gateway-ui.md) for template context/form/i18n changes, and
[Firmware app](firmware-app.md) for device payload changes. The remote CLI
must continue using HTTP; it does not own gateway files. Read both storage
and scheduler when changing midnight behavior. Dependency pins are in root
snapshot; no frontend dependencies or new runtime packages are required.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| --- | --- | --- |
| Wire fields / record behavior | Models, all write handlers, CLI and firmware decoder | Backward fields, point/intake/sleep cases, missing IDs, partner owners. |
| Auth / proxy | Dependency, middleware, Dockerfile command | Untrusted/allowed clients; direct/proxied IP; Bearer/Basic/cookie and shortcut. |
| Dates / summaries | Normalization, grouping, util, filters | Midnight + timezone + intake units; storage/scheduler/UI partners. |
| Browser form contract | Form handlers and context | UI owner; dialog/save/delete/config round-trip. |

## Verification

Run root setup/syntax commands. Local runtime from `gateway/`, using
throwaway state and a loopback listener:

```sh
BABYTIME_CHECK_DIR=$(mktemp -d)
GATEWAY_DB_PATH="$BABYTIME_CHECK_DIR/gateway.db" GATEWAY_CONFIG_PATH="$BABYTIME_CHECK_DIR/config.json" GATEWAY_TOKEN= .venv/bin/python -m uvicorn app.main:app --no-proxy-headers --host 127.0.0.1 --port 8080
```

After startup, from root in another terminal:

```sh
curl --fail --silent http://127.0.0.1:8080/api/state
python3 skill/scripts/babytime.py --host http://127.0.0.1:8080 activities
python3 skill/scripts/babytime.py --host http://127.0.0.1:8080 add --start '2026-09-23 12:00' --ml 90
python3 skill/scripts/babytime.py --host http://127.0.0.1:8080 dump 2026-09-23
```

Pass: valid state JSON, advertised activities, feeding stored 11:45–12:00
with default 15-minute duration, and day summary `total_ml=90`. Stop the
local process after checking; never aim mutation checks at an existing log.
For changed behavior also exercise PATCH/delete/day notes, cross-midnight
sleep versus intake clamp, and the authentication matrix above. Syntax and
an HTTP smoke alone do not establish security or all validation paths.

## Known Gaps

No committed API tests. Input amount ranges and several form failures lack
consistent client validation; record lists/day grouping read all rows in
some paths. Re-splitting a sleep does not remove previous siblings; minute
precision edits can shave 59 seconds from a midnight-clamped row. Form
writes have no CSRF token and auth is gateway-wide, with no roles/rate limit.
The proxy trust configuration and credential-bearing shortcut URL require
careful review when changed. These are existing limitations, not new scope.
