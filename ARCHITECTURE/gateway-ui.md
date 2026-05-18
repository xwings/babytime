# gateway-ui

## Goal

Browser-facing surface of the gateway: a single-page UI with two
top-right tabs (Records / Configuration), a feed-now panel with live
1 Hz elapsed-time counter and Start/Stop button, an Add-record form
with header-action button, and per-date collapsible record groups
with select-all + auto-check of the last 24 h for upload.

## Status

`done`.

## Code Structure

| File | Role |
| ---- | ---- |
| `gateway/app/templates/base.html` | Page chrome, header with right-aligned tabs, tab-switch IIFE |
| `gateway/app/templates/index.html` | Feed-now, Add-record, Records (date groups), Configuration sections + live-counter JS |
| `gateway/app/static/style.css` | Layout (grid for feed-now, flex+margin-left for tabs), date-group fold styling |

## Key Types and Entry Points

- `gateway/app/templates/base.html:12` — `<nav class="tabs">` with Records / Configuration buttons.
- `gateway/app/templates/base.html:20` — IIFE wiring tab buttons; reads initial tab from URL hash (`#records` / `#config`).
- `gateway/app/templates/index.html:12` — `<section class="feed-now">` with 3-column grid (detail | live counter | button); status text varies on `active`.
- `gateway/app/templates/index.html:36` — inline `<script>` defining `fmt(seconds)` + `tick()` that updates every `.live-elapsed` span once per second from its `data-since` epoch.
- `gateway/app/templates/index.html:63` — `<section class="add-record">` with header-row + top-right Add button; ml/Device prefilled from `config.default_volume_ml` / `config.default_device_id`.
- `gateway/app/templates/index.html:84` — `<section class="records">` — per-date `.date-group` blocks with chevron fold toggle, per-date select-all checkbox (indeterminate state when partial), 24 h auto-check (`row.start_epoch >= auto_check_cutoff`), header reads `{{ g.date }} ({{ g.records | length }})`.
- `gateway/app/templates/index.html:222` — `<section class="config">` (Configuration tab body).
- `gateway/app/static/style.css` — `.tabs { margin-left: auto }` (right-aligned tabs), `.feed-now-form` 3-col grid with mobile media-query stacking, `.feed-now-counter { font-variant-numeric: tabular-nums }`, `.date-group`/`.date-header`/`.fold-toggle` with chevron rotation transform.

## Interactions

- Rendered by [gateway-api.md](gateway-api.md) `ui_home`; receives
  `groups`, `last_finished`, `now_epoch`, `auto_check_cutoff`,
  `config`, `dates_per_page` from the route.
- Submits to [gateway-api.md](gateway-api.md): `/ui/feed`,
  `/records`, `/records/save`, `/records/delete`, `/config`,
  `/sync`.
- The live counter is purely client-side off the server-rendered
  `start_epoch` — there is no server push.

## How to Test

With the gateway running, open `http://localhost:8080/` in a browser.
Pass means all of:

- Feed-now panel renders with the elapsed-time counter centered
  between status text (left) and the Start/Stop button (right).
- Counter ticks once per second when a session is active.
- Clicking **Start feeding** posts `/ui/feed` and the page returns
  showing **Stop feeding** (no broken-state flash).
- Date headers collapse/expand on chevron click; each header shows
  `YYYY-MM-DD (N)`.
- Date-header checkbox toggles all rows in that day; rows from the
  last 24 h are pre-checked on page load.
- Tabs (Records / Configuration) sit on the right of the header and
  switch sections without a full reload.

## Open Gaps / Roadmap

- No live push: a feed started on another device only appears after
  a manual refresh (counter is client-side off the rendered
  `start_epoch`).
- No `localStorage` persistence of date-group fold state — every
  reload starts with the default (most-recent expanded) layout.
- No mobile-specific layout beyond the single media query that
  collapses the feed-now grid.
