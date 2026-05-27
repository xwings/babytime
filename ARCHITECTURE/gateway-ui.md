# gateway-ui

## Goal

Browser-facing surface of the gateway: a single-page UI with two
top-right tabs (Records / Configuration), a per-browser language
switch (English / 中文) seated to the left of the tabs, an
activity-button bar (one toggle per configured activity — blue when
idle, red with a live 1 Hz in-progress timer when running); the idle
Feeding button carries an integrated `Last fed:` live 1 Hz counter
since the most recent finished feeding, an Add-record form with
header-action button, and per-date collapsible record groups with select-all +
auto-check of the last 24 h. Each date group carries a full-width
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
| `gateway/app/static/style.css` | Layout (flex `.activity-bar`/`.activity-btn`, flex+margin-left for tabs), `.lang-switch` chip, `.day-note-block`, date-group fold styling |
| `gateway/app/i18n.py` | Translation tables (EN / ZH), cookie helpers, `t(key, lang, **kwargs)` substitution |

## Key Types and Entry Points

- `gateway/app/templates/base.html:12` — `<nav class="tabs">` ordered: language switch (EN / 中文), then Records / Configuration tab buttons.
- `gateway/app/templates/base.html:13-16` — `.lang-switch` anchors point at `/lang/{code}`; the active language gets `.active` from server-rendered `lang` context.
- `gateway/app/templates/base.html:22-28` — inline script populating `window.I18N` with unit strings (hour/minute/second) used by the live-elapsed counter — keeps Chinese rendering as `1时 30分` without a second roundtrip.
- `gateway/app/templates/base.html:30` — IIFE wiring tab buttons; reads initial tab from URL hash (`#records` / `#config`).
- `gateway/app/i18n.py:41-130` — `TRANSLATIONS` dict with EN + ZH covering nav, activity bar, records, columns, day-note, pagination, config, and unit strings.
- `gateway/app/i18n.py:142` — `normalize(code)` clamps any input to a supported lang or `DEFAULT_LANG`.
- `gateway/app/i18n.py:147` — `read_lang(request)` returns the cookie-backed lang.
- `gateway/app/i18n.py:151` — `t(key, lang, **kwargs)` looks up the entry and substitutes `{name}` placeholders with `str.replace` (no `str.format`, so any literal braces in a translated string pass through untouched).
- `gateway/app/templates/index.html` — `<section class="activity-bar">` renders one `<form action="/ui/activity">` per activity from `active_map`; the button is `.running` (red, `.live-elapsed` timer since `start_epoch`) when that activity has an open session, else `.idle` (blue). The idle Feeding button is special: when `last_fed` exists it shows an `.activity-sub` "Last fed:" label plus a `.live-elapsed` counter since `last_fed.stop_epoch`; otherwise (and for other idle activities) it shows the "tap to start" hint.
- `gateway/app/templates/index.html` — inline `<script>` defining `fmt(seconds)` + `tick()` that updates every `.live-elapsed` span once per second from its `data-since` epoch (drives the running-activity timer).
- `gateway/app/templates/index.html:63` — `<section class="add-record">` with header-row + top-right Add button; ml/Device prefilled from `config.default_volume_ml` / `config.default_device_id`.
- `gateway/app/templates/index.html:84` — `<section class="records">` — per-date `.date-group` blocks with chevron fold toggle, per-date select-all checkbox (indeterminate state when partial), 24 h auto-check (`row.start_epoch >= auto_check_cutoff`), header reads `{{ g.date }} ({{ g.records | length }}{% if g.total_ml %}, {{ g.total_ml }} ml{% endif %})`. Between the header and the records table, a `.day-note-block` holds the full-width `<textarea name="day_note_{date}">` (hidden when the group is collapsed; labelled "Notes for Today" when `g.date == now_date`, else "Day note"); it round-trips through `/records/save`. Each row has an `activity_{id}` `<select>` (`.activity-select`) for its activity; the Add-record form has no activity picker and defaults new records to feeding.
- `gateway/app/templates/index.html:222` — `<section class="config">` (Configuration tab body).
- `gateway/app/static/style.css` — `.tabs { margin-left: auto }` (right-aligned tabs), `.activity-bar` flex row of `.activity-btn.idle` (blue) / `.activity-btn.running` (red) buttons with a tabular-nums `.activity-timer` and an `.activity-sub` micro-label (the idle Feeding button's "Last fed:"), `.day-note-block`/`.day-note` textarea styling (`border-bottom`, sits between header and table), `.date-group`/`.date-header`/`.fold-toggle` with chevron rotation transform.

## Interactions

- Rendered by [gateway-api.md](gateway-api.md) `ui_home`; receives
  `groups` (each group carries `date`, `records`, `total_ml`, `note`),
  `activities`, `active_map` (`{activity: open-session}`),
  `last_fed` (most recent finished feeding, or `None`), `now_epoch`,
  `now_date`, `auto_check_cutoff`, `config`, `dates_per_page`, plus
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
  activity is blue ("tap to start"), a running one is red and shows a
  timer that ticks once per second.
- Clicking a blue button posts `/ui/activity` and the page returns
  with that button red + counting; clicking it again stops it.
- The idle Feeding button shows a `Last fed:` counter ticking once per
  second since the most recent finished feeding (just "tap to start"
  until one feeding has been stopped); while feeding is running the
  button is red and shows the in-progress timer instead.
- Date headers collapse/expand on chevron click; each header shows
  `YYYY-MM-DD (N)`.
- Date-header checkbox toggles all rows in that day; rows from the
  last 24 h are pre-checked on page load.
- Each date group has a multi-line day-note textarea between the date
  header and that date's records (labelled "Notes for Today" on the
  current date); editing it and clicking Save persists the note
  (round-trips on reload).
- Each row has an activity dropdown; the Add-record form has no
  activity picker and defaults new records to Feeding.
- Tabs (Records / Configuration) sit on the right of the header and
  switch sections without a full reload.
- Language switch chip (EN / 中文) sits left of the tabs; clicking
  the other language reloads the page in that language and the
  choice persists across reloads (cookie). Per-date headers show
  the day's millilitre total alongside the record count when at
  least one record that day has a volume logged.

## Open Gaps / Roadmap

- No live push: a feed started on another device only appears after
  a manual refresh (counter is client-side off the rendered
  `start_epoch`).
- No `localStorage` persistence of date-group fold state — every
  reload starts with the default (most-recent expanded) layout.
- No mobile-specific layout; the activity bar relies on flex-wrap to
  stack buttons on narrow screens rather than a dedicated breakpoint.
- i18n covers only EN + ZH today; adding a third language is one
  more dict in `app/i18n.py` plus a button in `base.html`. There
  is no `Accept-Language` auto-detection — the default is hard-
  coded to EN.
