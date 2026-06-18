# gateway-ui

## Goal

Browser-facing surface of the gateway: a single-page UI with two
top-right tabs (Records / Configuration), a per-browser language
switch (English / 中文) seated to the left of the tabs, an
activity-button bar (one button per configured activity). Activities
split into two kinds, set by the `timed_activities` config key: *timed*
ones (feeding, sleep) are start→stop toggles — blue when idle ("tap to
start"), red with a live 1 Hz in-progress timer when running; *instant*
ones (poopoo, etc.) log a single timestamp on tap ("tap to log") and
never enter a running state. The idle Feeding button carries an
integrated `Last fed:` live 1 Hz counter
since the most recent finished feeding; when that counter reaches
`feeding_alert_minutes` it shows "Time to feed?" and the idle top buttons
blink blue/red. Below the activity bar is an Add-record form with
header-action button, and per-date collapsible record groups (only today
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
- `gateway/app/i18n.py:28-136` — `TRANSLATIONS` dict with EN + ZH covering nav, activity bar, records, columns, day-note, pagination, config, and unit strings.
- `gateway/app/i18n.py:139` — `normalize(code)` clamps any input to a supported lang or `DEFAULT_LANG`.
- `gateway/app/i18n.py:149` — `read_lang(request)` returns the cookie-backed lang.
- `gateway/app/i18n.py:162` — `t(key, lang, **kwargs)` looks up the entry and substitutes `{name}` placeholders with `str.replace` (no `str.format`, so any literal braces in a translated string pass through untouched).
- `gateway/app/templates/index.html` — `<section class="activity-bar">` renders one `<form action="/ui/activity">` per activity from `active_map`; the button is `.running` (red, `.live-elapsed` timer since `start_epoch`) when that activity has an open session, else `.idle` (blue). The activity forms carry a client-side submit guard: after the first submit, the clicked button is disabled, marked `aria-busy`, and given `.is-pending` until navigation completes, so repeated taps cannot enqueue extra toggles. The idle Feeding button is special: when `last_fed` exists it shows an `.activity-sub` "Last fed:" label plus a `.live-elapsed` counter since `last_fed.stop_epoch`; if that elapsed time reaches `feeding_alert_minutes`, the button also shows `.activity-alert` "Time to feed?" and `.activity-bar.feeding-alert` makes every idle top button blink blue/red. Otherwise it shows the "tap to start" hint for timed activities (`a in timed`) and "tap to log" for instant ones. Instant activities never appear in `active_map` (their records are created closed, `stop == start`), so they have no running state.
- `gateway/app/templates/index.html` — inline `<script>` defining `fmt(seconds)` + `tick()` that updates every `.live-elapsed` span once per second from its `data-since` epoch (drives the running-activity timer).
- `gateway/app/templates/index.html:51` — `<section class="add-record">` with header-row + top-right Add button; ml/Device prefilled from `config.default_volume_ml` / `config.default_device_id`.
- `gateway/app/templates/index.html:77` — `<section class="records">` — per-date `.date-group` blocks with a chevron fold toggle. Only the `now_date` group renders expanded; every other date carries the `collapsed` class on initial render (template `{% if g.date != now_date %}collapsed{% endif %}`, toggled client-side thereafter). The date header has no select-all checkbox — selection/deletion is per-record only (`.row-check` plus the page-wide `check-all-btn`). Rows render unchecked (no auto-selection); the header reads `{{ g.date }} (<count> time(s)[, <total_ml> ml])` via the `date_count` i18n string, where `<count>` (`g.ml_count`) is the number of that day's records that carry a volume — feedings only; records without ml (sleep, poopoo, a feeding with no volume entered) are not counted, so the count and the ml total describe the same set. English pluralizes "time"/"times"; ml appended only when `g.total_ml` is nonzero. Between the header and the records table, a `.day-note-block` holds the full-width `<textarea name="day_note_{date}">` (hidden when the group is collapsed; labelled "Notes for Today" when `g.date == now_date`, else "Day note"); it round-trips through `/records/save`. Each row has an `activity_{id}` `<select>` (`.activity-select`) for its activity and a `notes_{id}` free-text `.notes-input` for that record's own note (blank clears it); the Add-record form carries its own `activity` `<select>` (`.add-activity-select`, options tagged with `data-timed`) and `notes` field, so any configured activity can be logged manually. Client-side validation reports an error when a timed record's stop time is more than 30 minutes after start; the server enforces the same rule. `/records` (`ui_create`) closes instant activities at creation (`stop_epoch = start_epoch`) and keeps the entered stop for timed ones. A row whose activity is instant (`r.activity not in timed`) renders its Stop and Duration cells as a static `—` (no editable stop input); `/records/save` re-closes such rows (`stop == start`).
- `gateway/app/templates/index.html:223` — `<section class="config">` (Configuration tab body). Activities are edited in a `.config-activities` fieldset: one `.activity-row` per activity with a name input and a `.timed-toggle` "timed" checkbox; a `+ Add activity` button appends a blank row (client-side, incrementing `activity_name_<i>` indices) and a per-row `×` removes one. The feeding row is read-only with a disabled (always-checked) timed box, reflecting that feeding is structurally required and always timed. The remaining scalar keys still render as plain text inputs from `config_keys_simple` (including `auto_stop_minutes`, `feeding_alert_minutes`, `default_volume_ml`, `timezone`, `ui_show_count` — `activity_types`/`timed_activities` are driven by the rows).
- `gateway/app/static/style.css` — `.tabs { margin-left: auto }` (right-aligned tabs), `.activity-bar` flex row of `.activity-btn.idle` (blue) / `.activity-btn.running` (red) buttons with a tabular-nums `.activity-timer` and an `.activity-sub` micro-label (the idle Feeding button's "Last fed:"), `.day-note-block`/`.day-note` textarea styling (`border-bottom`, sits between header and table), `.date-group`/`.date-header`/`.fold-toggle` with chevron rotation transform.
- `gateway/app/static/style.css` — `@media (max-width: 640px)` mobile layout (the only breakpoint; desktop is the default). The records `<table>` can't reflow as columns on a phone, so `thead` is hidden and each `<tr>` becomes a two-row card via CSS grid (`grid-template-columns: auto 1fr 1fr 1.3fr`, cells placed with `grid-area` by `:nth-child`): **row 1** is the "when" (checkbox · start · stop · duration), **row 2** the "what" (ml · activity · note, indented under the times). The bare volume gets its unit back with `td:nth-child(5)::after { content: attr(data-label) }` (the `data-label="{{ t('col_*') }}"` attrs on the cells in `index.html` survive from the table markup; only the ml cell renders one on mobile). Inputs bump to `font-size:16px` to stop iOS focus-zoom; header/tabs wrap full-width, `section`/`main` padding shrinks, `.bulk-actions` buttons stretch, and `.row-form` fields go full-width.

## Interactions

- Rendered by [gateway-api.md](gateway-api.md) `ui_home`; receives
  `groups` (each group carries `date`, `records`, `total_ml`, `note`),
  `activities`, `timed` (sorted list of timed activity names),
  `active_map` (`{activity: open-session}`, timed activities only),
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

- Activity bar renders one button per configured activity; an idle
  timed activity is blue ("tap to start"), a running one is red and
  shows a timer that ticks once per second. An instant activity (not in
  `timed_activities`) is blue with a "tap to log" hint and never turns
  red.
- Clicking a blue timed button posts `/ui/activity` and the page
  disables that button while the request is in progress, then returns
  with that button red + counting; clicking it again stops it.
  Clicking an instant button logs a single closed record (its row shows
  `—` for Stop and Duration) and the button stays idle.
- The idle Feeding button shows a `Last fed:` counter ticking once per
  second since the most recent finished feeding (just "tap to start"
  until one feeding has been stopped); while feeding is running the
  button is red and shows the in-progress timer instead.
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
  round-trips on Save (blank clears it); the Add-record form has its
  own activity dropdown (so any configured activity can be logged
  manually) and its own Note field. Adding an instant activity stores
  a closed record (`stop = start`); adding a timed one keeps the
  entered stop when it is within 30 minutes of start. Rows for an
  instant activity show `—` for Stop and Duration instead of an
  editable stop time.
- Tabs (Records / Configuration) sit on the right of the header and
  switch sections without a full reload.
- The Configuration tab lists each activity as a row with a name field
  and a "timed" checkbox; `+ Add activity` adds a row, `×` removes one,
  the feeding row is locked (read-only, always timed). Saving rebuilds
  `activity_types` + `timed_activities`, and the rows reflect the stored
  state on reload (feeding stays checked even though it isn't stored in
  `timed_activities`). It also has a Default-language `<select>`
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
- No mobile-specific layout; the activity bar relies on flex-wrap to
  stack buttons on narrow screens rather than a dedicated breakpoint.
- i18n covers only EN + ZH today; adding a third language is one
  more dict in `app/i18n.py` plus a button in `base.html`. There
  is no `Accept-Language` auto-detection — the default is hard-
  coded to EN.
