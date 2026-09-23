---
eatmycode_version: "2.1.0"
---
# Gateway UI Form Contract

Owner: [Gateway Browser UI](../modules/gateway-ui.md)

Read when: changing form field names, `data-*` hooks, browser-called endpoints, the `ui_home` template context or the configuration form in `gateway/app/templates/`.

## Contract

- Browser endpoints: fetch `GET /api/state` (consumes `server_epoch`,
  `active.start_epoch`, `last_feeding.stop_epoch`,
  `feeding_alert.threshold_minutes`; `feeding_alert.message` is unused) and
  fetch `POST /records/save` and `/records/delete` with FormData; native
  `POST /ui/activity` (`activity`, canonical key for built-ins, raw name for
  custom), `POST /records`, `POST /config` (redirects to `/#config`),
  `GET /lang/en|zh` and `?page=N`. Stylesheet loads as
  `/static/style.css?v=<tag>`; bump the tag on CSS edits.
- `/records` fields: `activity`, `amount`, `poopoo_amount|color|texture`,
  `supplement_type`, `notes` (two same-named textareas; only the enabled
  one submits), `date`, `start_time`, `end_time`. Sleep reuses the
  `data-etc-start-time-field` hook for its Start input; End stays disabled.
  Legacy `duration`, `stop_time` and `volume_ml` are server-accepted but no
  longer sent.
- `/records/save` fields: `record_id`, `activity_ID`, `date_ID`,
  `start_time_ID`, `stop_time_ID`, `amount_ID`, `notes_ID`, `day_note_DATE`;
  legacy `volume_ml_ID`/`volume_g_ID` accepted. The edit dialog renames
  `data-edit-field` inputs to `*_ID` on open and fills them from the
  entry's `data-record` JSON; `step="1"` keeps seconds. `/records/delete`
  posts `record_id` with `formnovalidate`.
- `/config` fields: `activity_name_N`, `activity_timed_N`,
  `poopoo_options_present` plus `poopoo_{amount|color|texture}_options_item_N`
  (prefix from `config.POOPOO_OPTION_KEYS` + `_item_`),
  `supplement_options_present` plus `supplement_options_item_N`,
  `default_language`, and the `config_keys_simple` inputs. Option inputs
  use `pattern="[^,]+"`; the server rejects commas with 400. Presence
  markers preserve intent when an option list is emptied.
- `ui_home` context: `request`, `lang`, `html_lang`, `t`, `al`, `pol`,
  `groups`, `activities`, `languages`, `timed`, `active_map`, `last_fed`,
  `feeding_alert` (`due`, `threshold_minutes`), `config`, `poopoo_options`,
  `supplement_options`, `tz`, `now_date`, `now_time`, `page`, `total_pages`,
  `dates_per_page` (unused), `max_record_duration_minutes`,
  `config_keys_simple`. Group keys: `date`, `records`, `note`, `milk_count`,
  `total_ml`, `food_count`, `total_g`, `sleep_count`, `sleep_hours`,
  `sleep_minutes`, `poopoo`. Record keys: `id`, `activity`, `start_epoch`,
  `stop_epoch`, `volume_ml`, `volume_g`, `notes`, `timeline_epoch`.
  `active_map` excludes solid_food/poopoo/supplement/etc.
- Jinja filters: `localdate_input(tz)`, `localtime_only(tz, exact_seconds)`;
  `localtime` is registered but unused. Translated strings reach JS through
  `window.I18N`, `data-*` attributes on `.activity-bar`,
  `[data-intake-dialog-field]` and the submit button, and `tojson` constants.

## Change and Verify

Field names and context keys are shared with [API](../modules/gateway-api.md)
handlers (`ui_create`, `ui_bulk_save`, `ui_bulk_delete`, `ui_save_config`,
`ui_home`); change both sides in one edit and keep legacy names accepted.
`test_timeline_orders_sleep_by_start_and_intake_by_end` and
`test_popup_notes_and_amount_edits_preserve_exact_times` in
`gateway/tests/test_sleep.py` post these field names; extend them for
renamed fields. Then run the browser steps in
[manual gateway checks](gateway-manual-checks.md).

## Evidence and Gaps

Sources: `index.html` form and dialog markup and inline script,
`base.html` head and tab script, `main.py` handlers and the context dict
in `ui_home`, `config.py` option key constants. Gaps: no test asserts the
`/config` field contract; `.sr-only` and `data-suffix` are unused
leftovers; two `col_ml`/`col_g` interpolations bypass `tojson`.
