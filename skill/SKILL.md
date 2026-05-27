---
name: babytime
description: babytime baby timer and activity recorder
metadata: {"author": "xwings", "openclaw": {"bins": ["python3 {baseDir}/scripts/babytime.py"]}}
---

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

Pass the gateway location on the command line (before the subcommand):

- `--host URL` — gateway base URL (default `http://127.0.0.1:8080`)
- `--token TOK` — bearer token; omit if the gateway is open on the LAN

Look up the host and token for this deployment in TOOLS.md.

## Record fields

| Field | Meaning |
| ----- | ------- |
| `id` | server-assigned record id |
| `start_epoch` / `stop_epoch` | session bounds, Unix seconds (`stop_epoch` null = still open) |
| `activity` | one of the gateway-configured types — run `activities` to list them; do not invent new ones |
| `volume_ml` | only meaningful for `feeding`; ignored/forced null for other activities |
| `notes` | free text |
| `device_id` | who recorded it (`agent` for this skill) |

When writing, you may give `start`/`stop` as either a Unix epoch or a
human time string `"YYYY-MM-DD HH:MM"`. Naive strings are interpreted in
the gateway's configured timezone — you do not need the UTC offset.

`activities` flags each type `timed` or instant. A **timed** activity
(e.g. feeding, sleep) is a `start`→`stop` session; give both bounds. An
**instant** activity (e.g. poopoo) is a single moment — give only
`start` and leave `stop` off.

## Helper script (preferred when shell is available)

`script/babytime.py` is a dependency-free Python 3 client:

```sh
python3 scripts/babytime.py --host https://gw.example.com --token abc123 activities
python3 scripts/babytime.py activities                         # [{activity, timed}, ...] — the types you may add
python3 scripts/babytime.py list --limit 10
python3 scripts/babytime.py list --activity feeding
python3 scripts/babytime.py add --start "2026-05-27 14:30" --stop "2026-05-27 14:45" --ml 90 --notes "left side"
python3 scripts/babytime.py add --activity sleep --start "2026-05-27 21:00"
python3 scripts/babytime.py update 12 --stop "2026-05-27 14:50" --ml 120
python3 scripts/babytime.py update 12 --activity poopoo        # volume is dropped automatically
python3 scripts/babytime.py delete 12

python3 scripts/babytime.py daynote get                        # {date: note} map of all day notes
python3 scripts/babytime.py daynote set 2026-05-27 --note "slept through the night"
python3 scripts/babytime.py daynote set 2026-05-27             # blank note clears the day's note
```

Non-2xx responses print to stderr and exit non-zero.

## Per-day notes

Each calendar date can hold one free-text note (a daily summary, say).
`GET /api/day_notes` returns a `{date: note}` map; `PUT /api/day_notes/{date}`
with `{"note": "..."}` upserts one day's note and a blank note clears it.
`date` must be `YYYY-MM-DD` in the gateway's timezone.
