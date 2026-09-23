---
eatmycode_version: "2.1.0"
---
# Gateway Manual Checks

Owner: [Gateway API](../modules/gateway-api.md)

Read when: verifying API, CLI, scheduler startup or browser behavior against a running gateway after changing `gateway/app/` or `skill/`.

## Contract

Start a throwaway gateway on a loopback listener from `gateway/` (venv per
root Verification):

```sh
BABYTIME_CHECK_DIR=$(mktemp -d)
GATEWAY_DB_PATH="$BABYTIME_CHECK_DIR/gateway.db" GATEWAY_CONFIG_PATH="$BABYTIME_CHECK_DIR/config.json" GATEWAY_TOKEN= .venv/bin/python -m uvicorn app.main:app --no-proxy-headers --host 127.0.0.1 --port 8080
```

API and CLI checks from root in another terminal:

```sh
curl --fail --silent http://127.0.0.1:8080/api/state
python3 skill/scripts/babytime.py --host http://127.0.0.1:8080 activities
python3 skill/scripts/babytime.py --host http://127.0.0.1:8080 add --start '2026-09-23 12:00' --ml 90
python3 skill/scripts/babytime.py --host http://127.0.0.1:8080 dump 2026-09-23
```

Pass: valid state JSON with `server_epoch`, the six default activities,
a feeding stored 11:45–12:00 (default 15-minute duration) and a day
summary with `total_ml=90`; `GET /` returns 200. Stopping the process
exits cleanly, which is the only observation of scheduler task
startup/shutdown. Stop it afterwards; never aim mutation checks at a real
log.

Browser checks for template, CSS, JavaScript or translation edits, at
`http://127.0.0.1:8080/` in a current browser:

1. At 360, 390, 768 and 1440 px render empty and populated logs in EN/ZH:
   no horizontal overflow, clipped controls or console errors.
2. Save all six quick-log modes, tap timeline entries to edit or delete,
   save/clear entry and day notes, change language, config and options.
   Only the selected entry mutates; timestamps, totals and ml/g survive
   reload. Check displayed-time sorting, exact midnight seconds, removed
   custom types, cancelled dialogs, invalid saves and fetch failure/retry.
3. Start/stop a custom timed activity and observe a remote Milk state
   update; counters keep localized units. Compare due Milk styling with
   alerts disabled. Start Sleep with an adjusted Start, cancel/reopen,
   reload and stop it: Start stays editable, End stays blank while open,
   a cross-midnight stop splits and the timer cap leaves it open.
4. Navigate tabs, dialogs and folds by keyboard; observe focus and ARIA
   state, long custom names, responsive labels and reduced-motion mode.

## Change and Verify

For changed API behavior also exercise PATCH/delete/day notes, cross-
midnight sleep versus intake clamp, and the auth matrix from the API
owner: untrusted and trusted-network clients, direct versus proxied IP,
Bearer, Basic, cookie and `?api=` with and without `shortcut`. Syntax
checks and this smoke do not establish security or every validation path.
Read the [UI owner](../modules/gateway-ui.md) before browser edits and the
[Scheduler owner](../modules/gateway-scheduler.md) for cap timing.

## Evidence and Gaps

The API/CLI sequence passed in this refresh on a loopback port with a
temporary database (Python 3.13 venv, pinned dependencies). No browser
check ran in this refresh; there is no committed browser suite and no
Safari/iOS or physical-device evidence. A screenshot alone cannot prove
submission, persistence or keyboard behavior.
