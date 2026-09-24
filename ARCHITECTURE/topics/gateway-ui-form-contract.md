---
eatmycode_version: "2.1.0"
---
# Gateway UI Form Contract

Owner: [Gateway Browser UI](../modules/gateway-ui.md)

Read when: changing form field names, `data-*` hooks, browser-called endpoints, the `ui_home` template context or the configuration form in `gateway/app/templates/`.

## Contract

- Browser endpoints: fetch `GET /api/state` (consumes `server_epoch`,
  `active.start_epoch`, `last_feeding.stop_epoch`,
  `feeding_alert.threshold_minutes`, `active.feeding_type`,
  `active_sleep.start_epoch`, `last_sleep.stop_epoch`, `today_poopoo`,
  `day_end_epoch`;
  `feeding_alert.message` is unused) and
  fetch `POST /records/save` and `/records/delete` with FormData; native
  `POST /ui/activity` (`activity`, canonical key for built-ins, raw name for
  custom), `POST /records`, `POST /config` (redirects to `/#config`),
  `GET /lang/en|zh` and `?page=N`. Stylesheet loads as
  `/static/style.css?v=<tag>`; bump the tag on CSS edits.
- `/records` fields: `activity`, `feeding_type`, `solid_food_type`, `amount`, `poopoo_amount|color|texture`,
  `supplement_type`, `notes` (two same-named textareas; only the enabled
  one submits), `date`, `start_time`, `end_time`. Sleep reuses the
  `data-etc-start-time-field` hook for its Start input; End stays disabled.
  Legacy `duration`, `stop_time` and `volume_ml` are server-accepted but no
  longer sent.
- `/records/save` fields: `record_id`, `activity_ID`, `date_ID`,
  `start_time_ID`, `stop_time_ID`, `amount_ID`, `feeding_type_ID`, `solid_food_type_ID`, `notes_ID`, `day_note_DATE`;
  legacy `volume_ml_ID`/`volume_g_ID` accepted. The edit dialog renames
  `data-edit-field` inputs to `*_ID` on open and fills them from the
  entry's `data-record` JSON. Time controls use `step="60"` and show `HH:MM`;
  `data-original-time` retains exact `HH:MM:SS` values. Unchanged enabled
  time inputs submit those original values via FormData, keeping stored
  seconds on notes/amount edits; changed times submit `HH:MM`. `/records/delete`
  posts `record_id` with `formnovalidate`.
- `/config` fields: `activity_name_N`, `activity_timed_N`,
  `poopoo_options_present` plus `poopoo_{amount|color|texture}_options_item_N`
  (prefix from `config.POOPOO_OPTION_KEYS` + `_item_`),
  `supplement_options_present` plus `supplement_options_item_N`,
  `solid_food_options_present` plus `solid_food_options_item_N`,
  `default_language`, `default_feeding_type`, and the `config_keys_simple` inputs. Option inputs
  use `pattern="[^,]+"`; the server rejects commas with 400. Food types also
  reject newlines and reserved Water (case-insensitive). Presence
  markers preserve intent when an option list is emptied.
- `ui_home` context: `request`, `lang`, `html_lang`, `t`, `al`, `pol`,
  `groups`, `activities`, `languages`, `timed`, `active_map`, `last_fed`,
  `button_activities` (preferred built-in card order, then custom types),
  `summary_activities` (four summary types from the same preferred order),
  `active_sleep`, `last_sleep`, `today_poopoo`, `day_end_epoch`, `server_epoch`,
  `feeding_alert` (`due`, `threshold_minutes`), `config`, `feeding_types`,
  `default_feeding_type`, `poopoo_options`,
  `supplement_options`, `solid_food_options`, `tz`, `now_date`, `now_time`, `page`, `total_pages`,
  `dates_per_page` (unused), `max_record_duration_minutes`,
  `config_keys_simple`. Group keys: `date`, `records`, `note`, `milk_count`,
  `total_ml`, `food_count`, `total_g`, `water_count`, `sleep_count`, `sleep_hours`,
  `sleep_minutes`, `sleep_duration`, `poopoo`. Record keys: `id`, `activity`, `start_epoch`,
  `stop_epoch`, `volume_ml`, `volume_g`, `feeding_type`, `solid_food_type`, `notes`, `timeline_epoch`.
  `active_map` excludes solid_food/poopoo/supplement/etc.
- Food selectors use `solid_food_type`: empty generic food, configured names,
  or reserved `water`. Water disables amount and editor Start; only its
  occurrence time is editable. Removed saved food names are inserted with
  `new Option` when opening the editor. Reminder ticks use `.activity-bar`
  data `last-fed-epoch` and `milk-active`.
- `.activity-bar` data `server-epoch` seeds the clock offset; `day-end-epoch`
  triggers a Poopoo count reset and state refresh at local midnight.
  `[data-poopoo-count]` holds the daily count; `last-sleep-label` and
  `activity-start-label`/`activity-stop-label` localize the polled Sleep card.
- Jinja filters: `localdate_input(tz)`, `localtime_only(tz, exact_seconds)`;
  `localtime` is registered but unused. Translated strings reach JS through
  `data-*` attributes on `.activity-bar`,
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
in `ui_home`, `config.py` option key constants. `gateway/tests/test_feeding.py` checks category/default form persistence.
Gaps: `.sr-only` and `data-suffix` are unused leftovers.
