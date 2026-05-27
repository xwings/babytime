# babytime Records

Use this skill when the user asks to read, add, correct, or delete
**babytime** baby-tracking records — feeding, sleep, poopoo, or any other
configured activity (e.g. "how many times did the baby feed today?",
"log a sleep from 9pm", "fix yesterday's 2pm bottle to 120ml", "delete
that duplicate entry") — or to read/write a **per-day note** (e.g.
"summarize today and save it as the day's note").

The records live in a SQLite database on the **babytime gateway**. You do
not (and cannot) open that database directly — it sits on the gateway
host. Instead you talk to the gateway over HTTP and it writes its own DB.

## Configuration

Two environment variables point the skill at a gateway:

- `BABYTIME_GATEWAY_URL` — base URL, e.g. `http://gateway.lan:8080`
  (default `http://127.0.0.1:8080`).
- `BABYTIME_GATEWAY_TOKEN` — bearer token. Required only if the gateway
  was started with a non-empty `GATEWAY_TOKEN`; sent as
  `Authorization: Bearer <token>`.

## Record fields

| Field | Meaning |
| ----- | ------- |
| `id` | server-assigned record id |
| `start_epoch` / `stop_epoch` | session bounds, Unix seconds (`stop_epoch` null = still open) |
| `activity` | `feeding`, `sleep`, `poopoo`, … (gateway-configurable) |
| `volume_ml` | only meaningful for `feeding`; ignored/forced null for other activities |
| `notes` | free text |
| `device_id` | who recorded it (`agent` for this skill) |

When writing, you may give `start`/`stop` as either a Unix epoch or a
human time string `"YYYY-MM-DD HH:MM"`. Naive strings are interpreted in
the gateway's configured timezone — you do not need the UTC offset.

## Helper script (preferred when shell is available)

`babytime.py` is a dependency-free Python 3 client:

```sh
export BABYTIME_GATEWAY_URL=http://gateway.lan:8080
export BABYTIME_GATEWAY_TOKEN=...        # omit if the gateway is open

python3 babytime.py list --limit 10
python3 babytime.py list --activity feeding
python3 babytime.py add --start "2026-05-27 14:30" --stop "2026-05-27 14:45" --ml 90 --notes "left side"
python3 babytime.py add --activity sleep --start "2026-05-27 21:00"
python3 babytime.py update 12 --stop "2026-05-27 14:50" --ml 120
python3 babytime.py update 12 --activity poopoo        # volume is dropped automatically
python3 babytime.py delete 12

python3 babytime.py daynote get                        # {date: note} map of all day notes
python3 babytime.py daynote set 2026-05-27 --note "slept through the night"
python3 babytime.py daynote set 2026-05-27             # blank note clears the day's note
```

Non-2xx responses print to stderr and exit non-zero.

## Raw HTTP (when shell/Python is unavailable)

```sh
URL=${BABYTIME_GATEWAY_URL:-http://127.0.0.1:8080}
AUTH="Authorization: Bearer ${BABYTIME_GATEWAY_TOKEN}"

# read newest 10
curl -s "$URL/api/records?limit=10" -H "$AUTH"

# add a feeding
curl -s -X POST "$URL/api/records" -H "$AUTH" -H 'content-type: application/json' \
  -d '{"start":"2026-05-27 14:30","stop":"2026-05-27 14:45","activity":"feeding","volume_ml":90}'

# correct a record (only the fields you send change)
curl -s -X PATCH "$URL/api/records/12" -H "$AUTH" -H 'content-type: application/json' \
  -d '{"volume_ml":120}'

# delete
curl -s -X DELETE "$URL/api/records/12" -H "$AUTH"

# read all per-day notes
curl -s "$URL/api/day_notes" -H "$AUTH"

# write one day's note (blank note clears it)
curl -s -X PUT "$URL/api/day_notes/2026-05-27" -H "$AUTH" -H 'content-type: application/json' \
  -d '{"note":"slept through the night"}'
```

`POST /api/records` requires `start`; everything else is optional and
`activity` defaults to `feeding`. `PATCH` updates only the fields you
include. Both return the stored record as JSON.

## Per-day notes

Each calendar date can hold one free-text note (a daily summary, say).
`GET /api/day_notes` returns a `{date: note}` map; `PUT /api/day_notes/{date}`
with `{"note": "..."}` upserts one day's note and a blank note clears it.
`date` must be `YYYY-MM-DD` in the gateway's timezone.
