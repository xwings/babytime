---
eatmycode_version: "2.1.0"
---
# Gateway Browser UI

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `gateway/app/templates/`, `gateway/app/static/`, `gateway/app/i18n.py`, browser interactions, accessibility or translations.

## Responsibility and Status

Implemented server-rendered Records/Configuration interface: six default
activity cards, a quick-log dialog, date summaries and flat daily timelines
with popup editing. Status **in progress**: no committed browser suite;
Chromium checks cover feeding add/edit/defaults and responsive EN/ZH flows. Owns presentation and browser state,
not persistence or time normalization. No bundler, remote fonts or
packages are used.

## Code Map

| Path / symbol | Role |
| --- | --- |
| `gateway/app/templates/base.html` | Head (stylesheet `?v=` cache-bust), skip link, language links, ARIA tabs with `hashchange`, main/footer. |
| `gateway/app/templates/index.html`: `renderFeeding`, `renderSleep`, `setDialogMode`, `syncFields` | Activity bar, quick-log dialog, timelines, record/day-note dialogs, configuration form and inline JavaScript. |
| `gateway/app/templates/icons.html`: `icon(name)` | Decorative inline SVG macro; imported in both templates because Jinja macros are not inherited. |
| `gateway/app/static/style.css` | Tokens, layout, `[data-activity]` colors, breakpoints and reduced-motion rules. |
| `gateway/app/i18n.py`: `TRANSLATIONS`, `t`, `activity_label`, `poopoo_option_label`, `read_lang` | EN/ZH strings, label helpers (`al`/`pol` in templates), cookie/default precedence. |

## Local Conventions

Follow [root conventions](../../ARCHITECTURE.md#code-conventions). Templates
use `t`, `al`, `pol`; `al` resolves `act_<name>` in the language, then EN,
then the raw name, so custom names keep their text. Serialize translated
JavaScript values with `tojson`. Strings reach JS through `data-*`
attributes and `tojson` constants, with hard-coded English fallbacks.
Icons are `aria-hidden`; controls keep text or accessible names. CSS tokens
are canonical; bump the stylesheet `?v=` query on CSS edits.

## Contracts and Invariants

- Tabs: panels `#panel-records`/`#panel-config` with `role=tablist/tab`,
  roving tabindex and Arrow/Home/End keys; URL hashes `#records`/`#config`
  select tabs via `hashchange`, and `POST /config` redirects to `/#config`
  (also the config section id). The skip link focuses main content.
- Language: `GET /lang/{code}` stores a cookie; any cookie beats
  `default_language`, and unknown values normalize to `en` without
  rejection. Supported set is EN/ZH; `t()` falls back language → EN → key.
  Nothing enforces EN/ZH pairing; both tables keep paired keys, and
  `col_stop`, `milk_decrease`, `milk_increase` are unused.
- Field names, `data-*` hooks, browser-called endpoints, `/config` inputs
  and `ui_home` context keys are contracts listed in the
  [UI form contract](../topics/gateway-ui-form-contract.md); read it before
  changing any of them and change API handlers in the same edit.
- Activity cards derive from configured types, displayed in Milk, Sleep,
  Poopoo, Solid food, Supplement, Etc order, then custom types in their
  configured order. Settings and API activity lists retain their own order.
  Icons key on the lowercased
  name, with `etc`/custom names falling back to a sparkle; colors come
  from `[data-activity]`. Idle Milk/Sleep and all Food/Poopoo/Supplement/Etc
  open the shared dialog; open Milk/Sleep close by submit; Sleep starts and
  stops regardless of its timed flag. Custom timed types toggle
  `/ui/activity`; other custom types log points. Busy guards block
  duplicate submits and reset on `pageshow`.
- Button 1 shows the configured feeding default and opens formula milk,
  breastfeeding and water choices; default formula. Each open resets the choice.
  Timeline/editor retain the saved category; legacy NULL still displays Milk.
- Dialog modes: Formula/Water/Food need an amount (±10 stepper, ml/ml/g);
  breastfeeding hides/disables amount. Only formula pre-fills default milk ml. Sleep posts
  Date plus adjustable Start with End hidden and disabled; Poopoo selects
  configured amount/color/texture; Supplement one option; Etc Start/End.
  Disabled controls are not submitted. Date/time defaults advance from
  rendered gateway wall time on each open. Native `<dialog>` supplies modal
  focus; Cancel, Escape and backdrop dismiss.
- Idle Sleep shows time since the latest completed sleep ended; active
  Sleep shows elapsed time since Start and keeps the stop action. With no
  history it shows the start hint. Poopoo shows Today's count, including 0,
  from 00:00 in the saved gateway timezone.
- Counters tick every second; `/api/state` polls every 30 s and on
  load/focus/visible, refreshing Milk, Sleep and the Poopoo count and correcting the
  clock offset; failed fetches keep rendered state. Due feeding uses amber
  styling without flashing. At the server-supplied next midnight, a tick
  clears the old Poopoo count and requests fresh state once; normal polling
  retries failures. The initial HTML also supplies the server clock offset.
- Clock times, live counters and timeline durations display
  zero-padded `HH:MM` in EN/ZH, omitting seconds; duration hours do not wrap
  at 24. Daily sleep summary chips and tooltips display `HH hours MM min`
  in EN and `HH 小时 MM 分钟` in ZH, retaining zero padding. Time inputs
  use minute precision. The editor retains exact times
  in its payload and submits the original seconds for unchanged inputs,
  preserving timestamps when only notes or amounts change.
- Timelines: dates and entries descend by `timeline_epoch`; today renders
  expanded, other dates `collapsed` with `<ol hidden>` and
  `aria-expanded=false`; summary chips for Milk, Food, Sleep and Poopoo
  always render, including zero totals; fold state is not persisted. Fold
  controls have a 48 px minimum height and a framed 40 px chevron. Each
  entry is a button carrying a `data-record` payload that opens
  `#edit-record-dialog`; Save posts to `/records/save`; Delete posts to
  `/records/delete` without validation. Intake Start is read-only, End
  editable, unit follows the activity; custom or deleted names stay
  selectable.
- Day notes: `#day-note-dialog` posts `day_note_DATE` to `/records/save`;
  blank clears. Both editors fetch, then reload on success; failures keep
  the dialog and values; duplicate submits are guarded.
- CSS: fixed six-column activity grid (three at ≤1050 px); breakpoints at
  1050/900/600 px; ≤600 px inputs use 16 px text; reduced-motion disables
  animation. `.sr-only` and `data-suffix` are unused.

## Dependencies and Boundaries

[API](gateway-api.md) supplies `ui_home` context and every mutation
endpoint; read it when changing field names, context, response handling
or timestamps. [Storage](gateway-storage.md) owns configuration/options
and canonical activity normalization; read it when changing built-in
behavior. Templates never open a database. Treat Jinja escaping, JSON
serialization and DOM text insertion as trust boundaries for record notes
and custom labels.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| --- | --- | --- |
| Layout / icons / breakpoints | Templates, icon macro, CSS, `?v=` query | Empty/populated EN/ZH at phone/tablet/desktop; keyboard/focus and long labels. |
| Dialog / record edits | Mode toggles, validators, handlers | Six default flows; units, popup save/delete, day notes, exact timestamps; API owner. |
| Timer / reminder | State polling, HH:MM timer formatting | EN/ZH minute precision, remote feeding update, due/disabled alerts, recovery. |
| Settings / localization | Config controls, translation maps | Form contract topic; add/remove activities/options, save/reload, feeding default/type persistence, cookie precedence, EN/ZH parity. |

## Verification

Run the root syntax check and unittest command;
`test_timeline_orders_sleep_by_start_and_intake_by_end` asserts rendered
HTML contains `day-timeline` and `edit-record-dialog` and no `row-check`.
Browser behavior is checked with the
[manual gateway checks](../topics/gateway-manual-checks.md) (read when
verifying template, CSS, JavaScript or translation edits). No frontend
build, lint or browser suite exists. Chromium checks pass for category/default
round-trips, null-volume edits and water reminder exclusion (including open Water).

## Known Gaps

No push channel; only Milk/Sleep cards and the Poopoo count refresh without reload. No persisted
fold state or unsaved-edit recovery. JavaScript and native `<dialog>` are
required for the quick-log flow; older-browser fallback is incomplete.
Safari/iOS and assistive-technology behavior are unverified.
