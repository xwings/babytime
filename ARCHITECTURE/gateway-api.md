# gateway-api

## Goal

HTTP surface for the gateway. Exposes the device-facing JSON API
(`/api/events`, `/api/state`, `/api/sync`, `/api/records`,
`/api/config`) that ESP32 firmware drives, plus the browser-facing
routes (`/`, `/ui/feed`, `/records*`, `/config`, `/sync`) that render
and mutate the same store through the web UI.

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
- `gateway/app/main.py:81` — `lifespan` — startup: `db.init()`, `config.migrate_from(...)`, spawn `openclaw.scheduler_loop` as a background task.
- `gateway/app/main.py:99` — `check_token` — `Authorization: Bearer <token>` dependency, no-op when `GATEWAY_TOKEN` is unset.
- `gateway/app/main.py:109` — `state_payload` — assembles `{active, history, server_epoch}` for `/api/state`.
- `gateway/app/main.py:128` — `POST /api/events` — start/stop toggle; honors `timestamp_epoch` override.
- `gateway/app/main.py:142` — `GET /api/state` — device polling target.
- `gateway/app/main.py:151` — `POST /api/sync` — explicit OpenClaw push (selected ids or newest N).
- `gateway/app/main.py:159` — `GET /api/records` — JSON record list (read-only).
- `gateway/app/main.py:164` — `GET /api/config` — non-secret config dump.
- `gateway/app/main.py:174` — `ui_home` (`GET /`) — groups records by local date, paginates by date count (`ui_show_count`).
- `gateway/app/main.py:261` — `POST /ui/feed` — web-initiated K2 mirror; stamps `device_id="web"`.
- `gateway/app/main.py:272` — `POST /records` — add via form.
- `gateway/app/main.py:299` — `POST /records/save` — inline edit.
- `gateway/app/main.py:329` — `POST /records/delete`.
- `gateway/app/main.py:338` — `POST /config` — saves the config form.
- `gateway/app/main.py:346` — `POST /sync` — UI sync; same as `/api/sync` but redirects back to `/`.

## Interactions

- Reads/writes through [gateway-storage.md](gateway-storage.md) for
  records and config on every route.
- Calls into [gateway-openclaw.md](gateway-openclaw.md) `send_sync`
  on `/api/sync` and `/sync`; `lifespan` launches
  `openclaw.scheduler_loop` (auto-stop + auto-sync).
- Renders templates owned by [gateway-ui.md](gateway-ui.md).

## How to Test

From `gateway/`:

```sh
docker compose up -d --build
curl -s http://localhost:8080/api/state | jq .
curl -s http://localhost:8080/ | grep -F 'feed-now'
```

- Pass = first `curl` prints a JSON object with `active`, `history`,
  and `server_epoch` keys.
- Pass = second `curl` prints at least one line containing
  `feed-now` (HTML rendered with the feed-now section).

## Open Gaps / Roadmap

- `/ui/*` and `/records*` routes are not behind `check_token`;
  LAN-trust is assumed. Could move under the same dependency when
  `GATEWAY_TOKEN` is set, but no work tracked yet.
- No per-route metrics, structured logging, or rate limiting.
