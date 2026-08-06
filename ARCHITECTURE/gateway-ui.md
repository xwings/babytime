# gateway-ui

## Goal

Browser-facing surface of the gateway: a single-page UI with Records /
Configuration tabs, language switching, and one activity button per
configured activity. Feeding is special: tapping it opens the same
Add-record dialog as the Add button, with a large phone-friendly milk
input, common-volume presets, and one explicit end time. It never starts
a new timer. Other activity types still follow `timed_activities`:
timed types such as sleep toggle start→stop, while point types log once.
The idle Feeding button carries an integrated `Last fed:` live counter;
after `feeding_alert_minutes` it shows "Time to feed?" and blinks. Below
the activity bar is an Add-record launcher and per-date collapsible groups (only today
expanded by default) with per-record selection (rows start unchecked). Each record row carries its own free-text
note field (distinct from the per-day note). Each date group carries a full-width
free-text day-note textarea seated between that date's header and
its records (labelled "Notes for Today" on the current date, "Day
note" otherwise), and per-date headers also show the day's `total_ml`
(omitted when zero, so days with no volume logged stay clean).

## Status

`done`.

## Code Structure

| File | Role |
| ---- | ---- |
| `gateway/app/templates/base.html` | Page chrome, header with language switch + right-aligned tabs, tab-switch IIFE, `window.I18N` JS bridge |
| `gateway/app/templates/index.html` | Activity-button bar, Add-record, Records (date groups + day-note textareas), Configuration sections + live-timer JS; every visible string routed through `t(...)` |
| `gateway/app/static/style.css` | Layout (flex `.activity-bar`/`.activity-btn`, flex+margin-left for tabs), `.lang-switch` chip, `.day-note-block`, date-group fold styling, `.config-activities` fieldset + `.activity-row`/`.timed-toggle` rows |
| `gateway/app/i18n.py` | Translation tables (EN / ZH), cookie helpers, `t(key, lang, **kwargs)` substitution |

## Key Types and Entry Points

- `gateway/app/templates/base.html:12` — `<nav class="tabs">` ordered: language switch (EN / 中文), then Records / Configuration tab buttons.
- `gateway/app/templates/base.html:13-16` — `.lang-switch` anchors point at `/lang/{code}`; the active language gets `.active` from server-rendered `lang` context.
- `gateway/app/templates/base.html:24-30` — inline script populating `window.I18N` with unit strings (hour/minute/second) used by the live-elapsed counter — keeps Chinese rendering as `1时 30分` without a second roundtrip.
- `gateway/app/templates/base.html:31` — IIFE wiring tab buttons; reads initial tab from URL hash (`#records` / `#config`).
- `gateway/app/i18n.py:28-140` — `TRANSLATIONS` dict with EN + ZH covering nav, activity bar, records, columns, day-note, pagination, config, and unit strings.
- `gateway/app/i18n.py:143` — `normalize(code)` clamps any input to a supported lang or `DEFAULT_LANG`.
- `gateway/app/i18n.py:153` — `read_lang(request)` returns the cookie-backed lang.
- `gateway/app/i18n.py:166` — `t(key, lang, **kwargs)` looks up the entry and substitutes `{name}` placeholders with `str.replace` (no `str.format`, so any literal braces in a translated string pass through untouched).
- `gateway/app/templates/index.html` — the activity bar keeps live Last fed / alert polling. Idle Feeding is a dialog opener; timed non-feeding buttons still submit guarded toggles. An open feeding left by old software is surfaced as running so one post can close it during upgrade.
- `gateway/app/templates/index.html` — `#add-record-dialog` is shared by the Feeding and Add buttons. It contains activity, date, end time, a large required feeding-volume input, 30–180 ml presets, and notes. The rendered gateway time advances while the page is open so each launch defaults to the current gateway wall time.
- `gateway/app/templates/index.html` — completed point rows show `—` for Start, expose an editable End time, and show no duration. Legacy/timed sessions retain Start, End, and duration. Editing a point end keeps both stored epochs equal.
- `gateway/app/templates/index.html` — the Configuration activity list locks Feeding as an end-time type; only other activities can be marked timed.
- `gateway/app/static/style.css` — desktop dialog/card/table styling plus the `max-width: 640px` layout. On phones the dialog fills `100dvh`, uses 16 px controls to avoid iOS zoom, keeps actions in a full-width footer, and gives the milk field/presets large touch targets.

## Interactions

- Rendered by [gateway-api.md](gateway-api.md) `ui_home`; receives
  `groups` (each group carries `date`, `records`, `total_ml`, `note`),
  `activities`, `timed` (sorted list of timed activity names),
  `active_map` (`{activity: open-session}` for timed activities plus any
  legacy open feeding during upgrade),
  `last_fed` (most recent finished feeding, or `None`),
  `now_date`, `config`, `dates_per_page`, plus
  `lang` / `html_lang` / `t` / `al` for the i18n layer.
- Submits to [gateway-api.md](gateway-api.md): `/ui/activity` (one
  form per activity button), `/records`, `/records/save` (persists
  both record edits and the per-date day notes), `/records/delete`,
  `/config`, and the language switch hits `/lang/{code}` (303 back to
  referer with the `lang` cookie set, max-age 1 year).
- The in-progress timer is purely client-side off the server-rendered
  `start_epoch` — there is no server push.
- Translation table lives in `app/i18n.py` and covers every visible
  string in both templates. Config field identifiers
  (`auto_stop_minutes`, `default_volume_ml`, …) are intentionally not
  translated — they're config keys, not labels.

## How to Test

With the gateway running, open `http://localhost:8080/` in a browser.
Pass means all of:

- Activity bar renders one button per configured activity. Feeding says
  "tap to log" and opens the Add-record dialog; other timed activities
  still show start/running states and point activities log immediately.
- Clicking a blue timed button posts `/ui/activity` and the page
  disables that button while the request is in progress, then returns
  with that button red + counting; clicking it again stops it.
  Clicking an instant button logs a single closed record (its row shows
  `—` for Start and Duration, with one End time) and the button stays idle.
- The idle Feeding button shows a `Last fed:` counter ticking once per
  second since the most recent finished feeding ("tap to log" until the
  first record). Clicking it opens a dialog requiring milk amount and
  labelling its single timestamp as End time.
- Date headers collapse/expand on chevron click; only today's group is
  expanded on load, every other date starts collapsed. Each header shows
  `YYYY-MM-DD (N times[, M ml])` — the count reads "1 time" / "6 times"
  and counts only that day's records with a volume (feedings), so it
  pairs with the millilitre total; the total is appended only when at
  least one record that day has a volume.
- There is no per-date select-all; selection and deletion are per-record
  (each row's checkbox, plus the page-wide "select all on page" button).
  Rows render unchecked — nothing is selected by default.
- Each date group has a multi-line day-note textarea between the date
  header and that date's records (labelled "Notes for Today" on the
  current date); editing it and clicking Save persists the note
  (round-trips on reload).
- Each row has an activity dropdown and a free-text Note field that
  round-trips on Save. The Add dialog can log any activity at one end
  time; for feeding it requires ml. Added records are closed points
  (`stop = start = end`). Point rows show `—` for Start/Duration and an
  editable End input; old/timed sessions retain their duration fields.
- Tabs (Records / Configuration) sit on the right of the header and
  switch sections without a full reload.
- The Configuration tab lists each activity as a row with a name field
  and a "timed" checkbox; `+ Add activity` adds a row, `×` removes one,
  the feeding row is locked as an end-time record. Saving rebuilds
  `activity_types` + `timed_activities`, ignoring any legacy Feeding
  entry in the timed set. It also has a Default-language `<select>`
  (`name="default_language"`) that seeds the UI language for browsers
  without a `lang` cookie.
- Language switch chip (EN / 中文) sits left of the tabs; clicking
  the other language reloads the page in that language and the
  choice persists across reloads (cookie). When no cookie is set the
  page falls back to the `default_language` set on the Configuration
  tab (`en`/`zh`). Per-date headers show
  the day's millilitre total alongside the record count when at
  least one record that day has a volume logged.

## Open Gaps / Roadmap

- No live push: a feed started on another device only appears after
  a manual refresh (counter is client-side off the rendered
  `start_epoch`).
- No `localStorage` persistence of date-group fold state — every
  reload starts with the default (only today's group expanded) layout.
- The mobile layout has a single `@media (max-width: 640px)` breakpoint;
  there is no intermediate tablet treatment, so 641–768 px viewports get
  the full desktop table.
- i18n covers only EN + ZH today; adding a third language is one
  more dict in `app/i18n.py` plus a button in `base.html`. There
  is no `Accept-Language` auto-detection — the default is hard-
  coded to EN.
