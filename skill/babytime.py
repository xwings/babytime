#!/usr/bin/env python3
"""babytime records client — stdlib-only HTTP CLI for the gateway API.

A remote agent never touches the gateway's SQLite file; it calls the
gateway over HTTP and the gateway writes its own DB. This script is that
HTTP client. No third-party packages: it runs on any Python 3.

Configuration (environment):
  BABYTIME_GATEWAY_URL    base URL, default http://127.0.0.1:8080
  BABYTIME_GATEWAY_TOKEN  bearer token; omit if the gateway is open on LAN

Examples:
  babytime.py list --limit 5
  babytime.py list --activity sleep
  babytime.py add --start "2026-05-27 14:30" --stop "2026-05-27 14:45" --ml 90
  babytime.py add --activity sleep --start "2026-05-27 21:00"
  babytime.py update 12 --activity poopoo
  babytime.py delete 12
  babytime.py daynote get
  babytime.py daynote set 2026-05-27 --note "slept through the night"
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("BABYTIME_GATEWAY_URL", "http://127.0.0.1:8080").rstrip("/")
TOKEN = os.environ.get("BABYTIME_GATEWAY_TOKEN", "").strip()


def _request(method: str, path: str, body: dict | None = None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if TOKEN:
        req.add_header("Authorization", "Bearer " + TOKEN)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        sys.exit(f"error: HTTP {e.code} {e.reason}: {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"error: cannot reach {url}: {e.reason}")
    return json.loads(raw) if raw else None


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


# Only forward flags the user actually set, so `update` stays a partial edit.
def _mutation_body(args) -> dict:
    body: dict = {}
    if args.start is not None:
        body["start"] = args.start
    if args.stop is not None:
        body["stop"] = args.stop
    if args.activity is not None:
        body["activity"] = args.activity
    if args.ml is not None:
        body["volume_ml"] = args.ml
    if args.notes is not None:
        body["notes"] = args.notes
    return body


def cmd_list(args) -> None:
    rows = _request("GET", f"/api/records?limit={args.limit}") or []
    if args.activity:
        rows = [r for r in rows if r.get("activity") == args.activity]
    _print(rows)


def cmd_add(args) -> None:
    if args.start is None:
        sys.exit("error: --start is required for add")
    _print(_request("POST", "/api/records", _mutation_body(args)))


def cmd_update(args) -> None:
    body = _mutation_body(args)
    if not body:
        sys.exit("error: nothing to update (pass at least one field)")
    _print(_request("PATCH", f"/api/records/{args.id}", body))


def cmd_delete(args) -> None:
    _print(_request("DELETE", f"/api/records/{args.id}"))


def cmd_daynote(args) -> None:
    if args.action == "get":
        _print(_request("GET", "/api/day_notes"))
    else:
        _print(_request("PUT", f"/api/day_notes/{args.date}", {"note": args.note}))


def _add_field_flags(p) -> None:
    p.add_argument("--start", help="epoch or 'YYYY-MM-DD HH:MM' (gateway tz)")
    p.add_argument("--stop", help="epoch or 'YYYY-MM-DD HH:MM' (gateway tz)")
    p.add_argument("--activity", help="feeding, sleep, poopoo, ... (default feeding on add)")
    p.add_argument("--ml", type=int, help="volume in ml (feeding only; ignored otherwise)")
    p.add_argument("--notes", help="free-text note")


def main() -> None:
    ap = argparse.ArgumentParser(description="babytime records HTTP client")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="list recent records (newest first)")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.add_argument("--activity", help="client-side filter by activity type")
    p_list.set_defaults(func=cmd_list)

    p_add = sub.add_parser("add", help="create a record")
    _add_field_flags(p_add)
    p_add.set_defaults(func=cmd_add)

    p_upd = sub.add_parser("update", help="patch an existing record by id")
    p_upd.add_argument("id", type=int)
    _add_field_flags(p_upd)
    p_upd.set_defaults(func=cmd_update)

    p_del = sub.add_parser("delete", help="delete a record by id")
    p_del.add_argument("id", type=int)
    p_del.set_defaults(func=cmd_delete)

    p_note = sub.add_parser("daynote", help="read or write per-day notes")
    note_sub = p_note.add_subparsers(dest="action", required=True)
    note_sub.add_parser("get", help="print the {date: note} map of all day notes")
    p_note_set = note_sub.add_parser("set", help="upsert one day's note (blank clears it)")
    p_note_set.add_argument("date", help="YYYY-MM-DD")
    p_note_set.add_argument("--note", default="", help="note text (omit to clear)")
    p_note.set_defaults(func=cmd_daynote)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
