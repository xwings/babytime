---
eatmycode_version: "2.1.0"
---
# Gateway API

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `gateway/app/main.py`, `gateway/app/util.py`, gateway runtime manifests, `skill/`, HTTP contracts, authentication or timestamps.

## Responsibility and Status

Implemented gateway transport/application boundary; status **in progress**
for complete behavioral/security coverage. Owns device state/events, record
and day-note JSON, browser form handlers, template context and the stdlib
HTTP CLI. Persistence, scheduling and presentation are partner owners.

## Code Map

| Path / symbol | Role |
| --- | --- |
| `gateway/app/main.py`: `require_auth`, `browser_api_key_link`, `_activity_card_state`, `state_payload`, `ui_home`, `RecordIn` | Auth boundary, key-link middleware, shared card summaries, device snapshot, browser context, input models (`EventIn`, `DayNoteIn`); route decorators locate endpoints. |
| `gateway/app/main.py`: `_to_epoch`, `_feeding_bounds`, `_segments`, `_stop_session`, `_record_date_epoch` | Time parsing, intake derivation, midnight wrapper, session close and day grouping. |
| `gateway/app/util.py`: `SPLIT_ACTIVITIES`, `zoneinfo`, `local_midnight_after`, `midnight_segments` | Split-rule switch and local-day segmentation shared with the scheduler. |
| `gateway/{requirements.txt,Dockerfile,docker-compose.yml}` | Dependency pins; uvicorn command with `GATEWAY_BIND_HOST/PORT` and `--no-proxy-headers`; env/persistence contract. |
| `skill/{SKILL.md,scripts/babytime.py}` | Agent instructions and stdlib argparse/urllib client; no SQLite access. |

## Local Conventions

Follow [root conventions](../../ARCHITECTURE.md#code-conventions). Async routes
call synchronous storage; Pydantic validates JSON; `HTTPException` reports
client errors. Forms skip unknown IDs and missing dates/times. Browser/device/
JSON paths share config, amounts and midnight helpers; retain legacy fields.

## Contracts and Invariants

- Routes use app-level `require_auth`; `/static` and FastAPI docs are outside
  it. Route decorators in `main.py` are the endpoint inventory. Record GET
  defaults to 100 newest-first or takes `date=YYYY-MM-DD`; missing IDs return
  404; blank day notes delete; successful form writes redirect 303.
- `lifespan` runs `db.init`, migrates absent JSON config from the legacy
  table, starts one scheduler task and cancels/awaits it on shutdown.
  `GATEWAY_TOKEN` is stripped at import; empty opens all routes. Saved
  `config.timezone`, not `TZ`, controls the calendar.
- With a token, trusted-network CIDRs bypass auth; otherwise Bearer, Basic
  password, the `babytime_access` cookie or a valid `?api=` key on `GET /`
  passes. Comparisons use `hmac.compare_digest`.
- `_effective_client_ip` walks `X-Forwarded-For` from the peer inward,
  skipping configured trusted proxies and invalid hops; keep uvicorn's
  `--no-proxy-headers` so the TCP peer stays intact.
- `browser_api_key_link`: a valid `GET /?api=` sets a year-long HttpOnly,
  SameSite=Lax, Secure HMAC-derived cookie and 303-strips the key unless
  `shortcut` is `1`/`true`/`yes`. Responses carry no-store/no-referrer.
  Plain-HTTP key links are not rejected, but the Secure cookie needs HTTPS.
- Epoch seconds are the wire format; `_to_epoch` also accepts ISO strings
  in the saved timezone. Milk/Food `start` means End with Start derived
  from `auto_stop_minutes`; Poopoo/Supplement are point rows; sleep is the
  only session that splits at local midnight, other closed spans clamp to
  their first day; device `log` records a feeding End. Read
  [record time rules](../topics/gateway-record-time-rules.md) before
  changing any timestamp, intake, sleep, split, device-event or grouping
  behavior; it holds the full contract and its gaps.
- `/api/state`: milk `active`/`last_feeding`, `today_feeds`/`today_ml`, eight
  mixed `history` rows, `server_epoch`, `feeding_duration_minutes`,
  `feeding_alert{due, elapsed_seconds, threshold_minutes, message}`.
  Browser fields: `active_sleep`/`last_sleep` (or null), `today_poopoo`
  (half-open local day), `day_end_epoch` (next midnight). `_activity_card_state`
  also serves `ui_home`; one epoch anchors clock/calendar. Firmware ignores
  additive fields.
- `feeding_type` is formula/breastfeeding; omitted creates use the configured
  default, edits preserve it (including legacy NULL). Breastfeeding has no ml.
  `solid_food_type` is NULL (generic food), a configured food name, or `water`.
  Unknown new choices return 400; removed saved choices survive unchanged edits.
  Other activities clear both category fields. Legacy `feeding_type=water`
  writes normalize to solid_food/water. Water has no ml/g, uses a point timestamp,
  and accepts device `log` only (start/stop return 400). Daily `water_count` is
  separate from food/milk totals and never resets Last fed.
- Poopoo/Supplement notes serialize as `Amount: x; Color: y; Texture: z;
  Extra notes: …` and `Supplement: x; Extra notes: …`; a configured option
  group without a valid selection is 400. `/config` rebuilds
  `activity_types`/`timed_activities` from `activity_name_N`/`activity_timed_N`,
  forces `etc` timed and strips built-in intake types. Food-option settings
  reject commas/newlines and reserved Water; the built-in Water choice remains.
- Popup editors post one `record_id` with `*_ID` fields to `/records/save`
  and `/records/delete`; legacy bulk and `volume_ml_ID`/`volume_g_ID`
  fields remain accepted. `ui_home` paginates dates (`page` clamped), not
  records, and exposes the context listed by the UI owner.
- CLI: global `--host`/`--token` before subcommands, Bearer auth, 15 s
  timeout, nonzero exit on errors; `add` needs `--start`; `update` forwards
  only supplied flags; `list` filters `--activity` after the server limit
  (default 20), so it may return fewer rows than requested.

## Dependencies and Boundaries

Read [Storage](gateway-storage.md) for schema/settings,
[Scheduler](gateway-scheduler.md) for lifespan/caps, [UI](gateway-ui.md) for
forms/i18n, [Firmware app](firmware-app.md) for device payloads, storage and
scheduler for midnight rules. CLI uses HTTP; pins are in the root snapshot.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| --- | --- | --- |
| Wire fields / record behavior | Models, all write handlers, CLI and firmware decoder | Record time rules topic; backward fields, point/intake/sleep cases, missing IDs, partner owners. |
| Auth / proxy | Dependency, middleware, Dockerfile command | Untrusted/allowed clients; direct/proxied IP; Bearer/Basic/cookie/key and shortcut. |
| Dates / summaries | Normalization, grouping, util, filters | Record time rules topic; midnight + timezone + intake units; storage/scheduler/UI partners. |
| Browser form contract | Form handlers and context | UI owner; dialog/save/delete/config round-trip. |

## Verification

Run the root syntax check and unittest command. `gateway/tests/test_sleep.py`
covers sleep sessions/splits, timeline ordering, exact timestamp preservation,
card/summary order, Poopoo boundaries and daylight-saving days.
`gateway/tests/test_feeding.py` covers milk/food/water categories, config,
migration, validation, edits, device defaults and water totals. For route, auth, CLI or time changes run the
[manual gateway checks](../topics/gateway-manual-checks.md) (read when
verifying behavior against a running gateway); its API/CLI sequence passed
in this refresh.

## Known Gaps

Tests cover Sleep, feeding categories/defaults and timeline edits; other paths
rely on manual checks. Time-handling defects are listed in the record time
rules topic. Amount ranges and some form failures lack validation; some
list/grouping paths read all rows. No CSRF token; auth is gateway-wide with
no roles or rate limit. `gateway/README.md` names `BABYTIME_GATEWAY_URL/TOKEN`
env vars that no code reads (the CLI uses flags) and omits `/api/activities`,
`/api/records?date=` and `/lang/{code}`.
