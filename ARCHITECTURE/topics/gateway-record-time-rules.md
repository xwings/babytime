---
eatmycode_version: "2.1.0"
---
# Gateway Record Time Rules

Owner: [Gateway API](../modules/gateway-api.md)

Read when: changing timestamps, intake derivation, sleep sessions, midnight splitting, device events or day grouping in `gateway/app/main.py` or `gateway/app/util.py`.

## Contract

- Parsing: `_to_epoch` accepts epoch numbers or ISO strings; naive strings
  use the saved `config.timezone`, and `util.zoneinfo` falls back to UTC on
  any error. `/api/events` takes an int `timestamp_epoch` only. Form paths
  combine `date` with `HH:MM` or `HH:MM:SS` through `combine_date_time`.
- Intake (Milk `feeding`, `solid_food`): `start` means End for
  compatibility and an explicit `stop` wins. `_feeding_bounds` sets Start to
  `max(0, end − auto_stop_minutes*60)` and keeps the first midnight segment,
  so an intake at 00:05 is stored 23:50–23:59:59 and grouped on the previous
  day. Poopoo/Supplement are point rows with equal bounds. `volume_ml` is
  Milk-only and `volume_g` Food-only.
- Explicit spans: normalized spans cap at 30 minutes except sleep (24 h);
  an earlier stop is read as the next day. Legacy completed sleep accepts
  `HH:MM` `duration` up to 23:59; Etc takes Start/End.
- Sleep sessions: the browser opens sleep with Date plus an adjustable
  Start regardless of the timed flag. `/records` rejects malformed or future
  open starts and redirects a duplicate open start without creating a row;
  `/records/save` rejects a future Start while Sleep is open. Sleep closes
  via `/ui/activity`, device `stop`/`log`, PATCH `stop` or `/records/save`
  `stop_time`; the scheduler never caps it.
- Segmentation: closed spans pass `_segments` (adds the config timezone)
  into `midnight_segments`. Sleep, the only `SPLIT_ACTIVITIES` member,
  yields one row per local day ending 23:59:59 and starting 00:00 with no
  zero-length tail; other types clamp to the start day. Open spans return
  `[(start, None)]`. Existing rows are never backfilled. `_create_segments`
  returns the first row and `clone_segments` writes siblings without intake
  amounts; `_update_segments` re-splits non-intake time edits.
- PATCH: a new activity nulls the other unit column, and an activity sent
  without an amount nulls the amount; bounds re-derive for intake and point
  types when start, stop or activity change.
- Device events (`/api/events`): `start` opens a row only if none of that
  activity is active; `stop` closes the newest via `_stop_session` with no
  duration guard; `log` records a feeding End (normalizing a legacy open
  feeding), always a point row for poopoo/supplement, and close-or-point
  for other timed types. Device rows receive `default_volume_ml`.
- Grouping and order: `_record_date_epoch` (canonical names) groups
  completed Milk/Food/Sleep/Poopoo/Supplement by End and others by Start.
  `ui_home` sorts dates descending and entries by `timeline_epoch` (raw
  names: intake/point End, session Start, id tie-break); JSON list order is
  unchanged. `GET /api/records?date=` returns oldest-first rows, the day
  note and milk/food/poopoo/sleep totals; `feeds` counts truthy `volume_ml`.
- Preservation: `/records/save` with unchanged exact Date/Start/End/activity
  keeps the original epochs on notes/amount edits, including midnight
  seconds and intake bounds after duration config changes.

## Change and Verify

Read [Storage](../modules/gateway-storage.md) for `clone_segments` and
`stop_active` semantics and [Scheduler](../modules/gateway-scheduler.md),
which applies the same clamp to caps. Firmware decodes `/api/state`
epochs; read [Firmware app](../modules/firmware-app.md) for field changes.
`gateway/tests/test_sleep.py` covers adjusted/duplicate/invalid/future
starts, manual-stop split, legacy duration, future Start edit, timeline
order and exact preservation; extend it for new rules. Run the root
unittest command and the [manual gateway checks](gateway-manual-checks.md)
for cross-midnight sleep versus intake clamp.

## Evidence and Gaps

Sources: `main.py` (`_to_epoch`, `_feeding_bounds`, `_segments`,
`_create_segments`, `_update_segments`, `_stop_session`,
`_record_date_epoch`, `ui_home`) and `util.py` (`SPLIT_ACTIVITIES`,
`local_midnight_after`, `midnight_segments`). Gaps: `/records` with
`end_time` and a malformed date/time raises an uncaught `ValueError` (500)
while the start-only path returns 400; `timeline_epoch` and
`_record_date_epoch` disagree for legacy alias rows; re-splitting a sleep
does not remove previous siblings; minute-only legacy edits can shave 59
seconds from a midnight-clamped row; fixed-duration intake and device
start/stop paths do not share one duration guard.
