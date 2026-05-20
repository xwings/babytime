# gateway-ui

## Goal

Browser-facing surface of the gateway: a single-page UI with two
top-right tabs (Records / Configuration), a per-browser language
switch (English / 中文) seated to the left of the tabs, a feed-now
panel with live 1 Hz elapsed-time counter and Start/Stop button, an
Add-record form with header-action button, and per-date collapsible
record groups with select-all + auto-check of the last 24 h for
upload. Per-date headers also show the day's `total_ml` (omitted
when zero, so days with no volume logged stay clean).

## Status

`done`.

## Code Structure

| File | Role |
| ---- | ---- |
| `gateway/app/templates/base.html` | Page chrome, header with language switch + right-aligned tabs, tab-switch IIFE, `window.I18N` JS bridge |
| `gateway/app/templates/index.html` | Feed-now, Add-record, Records (date groups), Configuration sections + live-counter JS; every visible string routed through `t(...)` |
| `gateway/app/static/style.css` | Layout (grid for feed-now, flex+margin-left for tabs), `.lang-switch` chip, date-group fold styling |
| `gateway/app/i18n.py` | Translation tables (EN / ZH), cookie helpers, `t(key, lang, **kwargs)` substitution |

## Key Types and Entry Points

- `gateway/app/templates/base.html:12` — `<nav class="tabs">` ordered: language switch (EN / 中文), then Records / Configuration tab buttons.
- `gateway/app/templates/base.html:13-16` — `.lang-switch` anchors point at `/lang/{code}`; the active language gets `.active` from server-rendered `lang` context.
- `gateway/app/templates/base.html:22-28` — inline script populating `window.I18N` with unit strings (hour/minute/second) used by the live-elapsed counter — keeps Chinese rendering as `1时 30分` without a second roundtrip.
- `gateway/app/templates/base.html:30` — IIFE wiring tab buttons; reads initial tab from URL hash (`#records` / `#config`).
- `gateway/app/i18n.py:41-130` — `TRANSLATIONS` dict with EN + ZH covering 38 keys (nav, feed-now, records, columns, pagination, config, sync banner, unit strings).
- `gateway/app/i18n.py:142` — `normalize(code)` clamps any input to a supported lang or `DEFAULT_LANG`.
- `gateway/app/i18n.py:147` — `read_lang(request)` returns the cookie-backed lang.
- `gateway/app/i18n.py:151` — `t(key, lang, **kwargs)` looks up the entry and substitutes `{name}` placeholders with `str.replace` (no `str.format`, so literal braces in `config_template_hint_html` pass through untouched).
- `gateway/app/templates/index.html:12` — `<section class="feed-now">` with 3-column grid (detail | live counter | button); status text varies on `active`.
- `gateway/app/templates/index.html:36` — inline `<script>` defining `fmt(seconds)` + `tick()` that updates every `.live-elapsed` span once per second from its `data-since` epoch.
- `gateway/app/templates/index.html:63` — `<section class="add-record">` with header-row + top-right Add button; ml/Device prefilled from `config.default_volume_ml` / `config.default_device_id`.
- `gateway/app/templates/index.html:84` — `<section class="records">` — per-date `.date-group` blocks with chevron fold toggle, per-date select-all checkbox (indeterminate state when partial), 24 h auto-check (`row.start_epoch >= auto_check_cutoff`), header reads `{{ g.date }} ({{ g.records | length }}{% if g.total_ml %}, {{ g.total_ml }} ml{% endif %})`.
- `gateway/app/templates/index.html:222` — `<section class="config">` (Configuration tab body).
- `gateway/app/static/style.css` — `.tabs { margin-left: auto }` (right-aligned tabs), `.feed-now-form` 3-col grid with mobile media-query stacking, `.feed-now-counter { font-variant-numeric: tabular-nums }`, `.date-group`/`.date-header`/`.fold-toggle` with chevron rotation transform.

## Interactions

- Rendered by [gateway-api.md](gateway-api.md) `ui_home`; receives
  `groups` (each group carries `date`, `records`, `total_ml`),
  `last_finished`, `now_epoch`, `auto_check_cutoff`, `config`,
  `dates_per_page`, plus `lang` / `html_lang` / `t` for the i18n
  layer.
- Submits to [gateway-api.md](gateway-api.md): `/ui/feed`,
  `/records`, `/records/save`, `/records/delete`, `/config`,
  `/sync`, and the language switch hits `/lang/{code}` (303 back to
  referer with the `lang` cookie set, max-age 1 year).
- The live counter is purely client-side off the server-rendered
  `start_epoch` — there is no server push.
- Translation table lives in `app/i18n.py` and covers every visible
  string in both templates. Config field identifiers
  (`webhook_url`, `default_volume_ml`, …) are intentionally not
  translated — they're config keys, not labels.

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
- No mobile-specific layout beyond the single media query that
  collapses the feed-now grid.
- i18n covers only EN + ZH today; adding a third language is one
  more dict in `app/i18n.py` plus a button in `base.html`. There
  is no `Accept-Language` auto-detection — the default is hard-
  coded to EN.
- Operational error messages from `openclaw.send_sync` (rendered
  after the sync banner prefix) remain in English; only the
  banner prefix is translated.
