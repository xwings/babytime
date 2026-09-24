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
   reload. Check HH:MM clock times, timeline durations and input values in
   EN/ZH; daily sleep summary chips and tooltips show `HH hours MM min`
   in EN and `HH 小时 MM 分钟` in ZH, including zero totals.
   Notes/amount-only edits must preserve stored seconds, including
   midnight `23:59:59`. Check displayed-time sorting, removed
   custom types, cancelled dialogs, invalid saves and fetch failure/retry.
3. Start/stop a custom timed activity and observe a remote Milk state
   update; counters show HH:MM at 00:00, 00:59 and 01:00 and beyond 24 hours.
   Compare due Milk styling with
   alerts disabled. Start Sleep with an adjusted Start, cancel/reopen,
   reload and stop it: Start stays editable, End stays blank while open,
   a cross-midnight stop splits and the timer cap leaves it open.
4. Navigate tabs, dialogs and folds by keyboard; observe focus and ARIA
   state, long custom names, responsive labels and reduced-motion mode.
5. Confirm card order Milk, Sleep, Poopoo, Solid food / Water, Supplement, Etc,
   followed by configured custom activities; summaries follow the same
   order for their four categories. The food button is 辅食/水 in Chinese.
   Milk offers only formula/breastfeeding. Add/remove food types in settings,
   save/reload and log a selected type with grams. Water has no amount control
   on add/edit, persists as a point without ml/g and has a separate daily count.
   Edit a record after removing its food type; the saved type must survive.
   Switch food ↔ water and verify quantities and bounds. Idle Sleep shows HH:MM since
   its latest End; a remote start switches to elapsed Start and a stop
   action, and a remote stop restores the idle timer. Poopoo shows today's
   count (including 0), refreshes after remote edits, and resets at saved-
   timezone 00:00 with the page open. Check records immediately before/at
   midnight and retry after a failed midnight refresh.

## Change and Verify

For changed API behavior also exercise PATCH/delete/day notes, cross-
midnight sleep versus intake clamp, and the auth matrix from the API
owner: untrusted and trusted-network clients, direct versus proxied IP,
Bearer, Basic, cookie and `?api=` with and without `shortcut`. Syntax
checks and this smoke do not establish security or every validation path.
Read the [UI owner](../modules/gateway-ui.md) before browser edits and the
[Scheduler owner](../modules/gateway-scheduler.md) for cap timing.

## Evidence and Gaps

API/CLI and Chromium checks passed against disposable loopback storage:
EN/ZH responsive layouts, all quick-log modes, food options, water quantities,
summary order, edits/deletes, exact timestamps and keyboard behavior. There
is no committed browser suite or Safari/iOS/physical-device evidence.
