---
eatmycode_version: "2.1.0"
---
# Gateway Browser UI

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `gateway/app/templates/`, `gateway/app/static/`, `gateway/app/i18n.py`, browser interactions, accessibility or translations.

## Responsibility and Status

Implemented server-rendered Records/Configuration interface: six default
activity cards, a quick-log dialog, date summaries and flat daily timelines
with popup editing. Status **in progress**: no committed browser suite.
Owns presentation and browser state; no bundler or frontend packages.

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
- Language: `GET /lang/{code}` stores a cookie overriding `default_language`;
  unknown values normalize to EN. `t()` falls back language → EN → key.
  Keep EN/ZH keys paired.
- Field names, `data-*` hooks, browser-called endpoints, `/config` inputs
  and `ui_home` context keys are contracts listed in the
  [UI form contract](../topics/gateway-ui-form-contract.md); read it before
  changing any of them and change API handlers in the same edit.
- Activity cards derive from configured types, displayed in Milk, Sleep,
  Poopoo, Solid food / Water (辅食/水), Supplement, Etc order, then custom types in their
  configured order. Settings and API activity lists retain their own order.
  Icons use lowercase names (custom fallback: sparkle); colors use
  `[data-activity]`. Idle Milk/Sleep and all Food/Poopoo/Supplement/Etc
  open the shared dialog; open Milk/Sleep close by submit; Sleep starts and
  stops regardless of its timed flag. Custom timed types toggle
  `/ui/activity`; other custom types log points. Busy guards block
  duplicate submits and reset on `pageshow`.
- Button 1 shows the configured feeding default: formula milk or breastfeeding.
  Each open resets the choice; legacy NULL still displays Milk.
- Solid food / Water offers generic food, configured food types, and Water.
  The timeline shows the saved type; removed types remain editable on old rows.
  Water hides/disables amount and records one timestamp; its daily count is
  separate from food grams and milk totals.
- Dialog modes: Formula/Food need an amount (±10 stepper, ml/g);
  breastfeeding and Water hide/disable amount. Only formula pre-fills milk ml. Sleep posts
  Date plus adjustable Start with End hidden and disabled; Poopoo selects
  configured amount/color/texture; Supplement one option; Etc Start/End.
  Disabled controls are not submitted. Date/time defaults advance on each
  open. Native `<dialog>` supplies focus; Cancel, Escape and backdrop dismiss.
- Idle Sleep shows time since the latest completed sleep ended; active
  Sleep shows elapsed time since Start and keeps the stop action. With no
  history it shows the start hint. Poopoo shows Today's count, including 0,
  from 00:00 in the saved gateway timezone.
- Counters tick each second; `/api/state` polls every 30 s and on
  load/focus/visible to refresh Milk/Sleep/Poopoo and clock offset. Failed
  fetches retain rendered state. Due feeding is amber without flashing.
  Server-supplied midnight clears Poopoo and requests state; polling retries.
- Times/counters/durations use zero-padded `HH:MM`; hours do not wrap at 24.
  Sleep summaries use `HH hours MM min` / `HH 小时 MM 分钟`.
  Unchanged minute-precision editor inputs submit original seconds, preserving
  timestamps on notes/amount edits.
- Timelines: dates and entries descend by `timeline_epoch`; today renders
  expanded, other dates `collapsed` with `<ol hidden>` and
  `aria-expanded=false`; summaries share the button sequence: Milk, Sleep,
  Poopoo, Food/Water, including zero totals. Fold state is not persisted. Each
  entry is a button carrying a `data-record` payload that opens
  `#edit-record-dialog`; Save posts to `/records/save`; Delete posts to
  `/records/delete` without validation. Intake Start is read-only (hidden for
  Water), End editable, unit follows the type; custom or deleted names stay
  selectable.
- Day notes: `#day-note-dialog` posts `day_note_DATE` to `/records/save`;
  blank clears. Both editors fetch, then reload on success; failures keep
  the dialog and values; duplicate submits are guarded.
- CSS: fixed six-column activity grid (three at ≤1050 px); breakpoints at
  1050/900/600 px; ≤600 px inputs use 16 px text; reduced-motion disables
  animation.

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

Run root syntax/unittest checks (feeding categories and timeline/summary order).
Use the
[manual gateway checks](../topics/gateway-manual-checks.md) (read when
verifying template, CSS, JavaScript or translation edits). No frontend
build, lint or browser suite exists. Disposable Chromium checks cover EN/ZH
at 360/390/768/1440 px, food settings, water add/edit, removed types, timestamp
preservation, and all six quick-log modes.

## Known Gaps

No push channel; only Milk/Sleep cards and the Poopoo count refresh without reload. No persisted
fold state or unsaved-edit recovery. JavaScript and native `<dialog>` are
required for the quick-log flow; older-browser fallback is incomplete.
Safari/iOS and assistive-technology behavior are unverified.
