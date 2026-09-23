---
eatmycode_version: "2.0.0"
---
# Gateway Browser UI

Owner: [Project architecture](../../ARCHITECTURE.md)

Read when: changing `gateway/app/templates/`, `gateway/app/static/`, `gateway/app/i18n.py`, browser interactions, accessibility or translations.

## Responsibility and Status

Implemented server-rendered Records/Configuration interface, redesigned
with cream/sage surfaces, six default activity cards, date summaries and
flat daily timelines with popup editing. Status **in progress** for exhaustive browser
coverage; local Chromium interaction checks pass. Owns presentation and
browser state, not record persistence or time normalization. No frontend
bundler, remote fonts, image service or new package is required.

## Code Map

| Path / symbol | Role |
| --- | --- |
| `gateway/app/templates/base.html` | Brand/header, language controls, keyboard tabs, skip link, I18N initialization and main/footer. |
| `gateway/app/templates/index.html`: `renderFeeding`, `setDialogMode`, `syncFields` | Activity state, quick-log dialog, daily timeline, record/day-note dialogs, configuration and inline JavaScript. |
| `gateway/app/templates/icons.html`: `icon` | Local decorative inline SVG macro; unknown/custom activities get a fallback symbol. |
| `gateway/app/static/style.css` | Shared palette/layout/control styles, responsive rules and reduced-motion handling. |
| `gateway/app/i18n.py`: `t`, `read_lang` | EN/ZH strings, labels and cookie/default language precedence. |

## Local Conventions

Follow [root conventions](../../ARCHITECTURE.md#code-conventions). Templates
use `t`, `al`, `pol` for translated copy and built-in labels; custom names
retain their entered text. Config labels are human-readable while submitted
keys stay stable. Serialize translated JavaScript values with Jinja `tojson`;
`window.I18N` must initialize in the head before content scripts capture it.
Icons are decorative/hidden from assistive technology; controls retain text
or accessible names. CSS tokens are canonical for palette/control styling.

## Contracts and Invariants

- Records/Configuration tabs use `#records`/`#config`, tab roles and roving
  tabindex. Arrow keys/Home/End activate/focus tabs. The skip link focuses
  main content. Language controls hit `/lang/{code}`; cookie overrides
  configured default, then English fallback. EN/ZH are the supported set.
- Activity cards derive from configured types. Idle Milk/Sleep and all
  Solid food/Poopoo/Supplement/Etc open the shared dialog. Existing open
  Milk/Sleep can be closed by form submission; Sleep shows a stop hint while
  running. Sleep always starts/stops even if its saved timed flag is off.
  Custom timed types toggle
  `/ui/activity`, while other custom types log points. Busy guards prevent
  duplicate activity-button submits and recover on browser pageshow.
- Milk/Food modes require an amount, with +/-10 step controls and ml/g unit.
  Sleep submits Date and adjustable Start to open a session; End is hidden
  and disabled. The next Sleep card press stops it. Poopoo
  selects configured amount/color/texture plus notes; Supplement chooses
  a configured option; Etc takes Start/End and notes. Irrelevant controls
  are disabled so their fields are not submitted. Date/time defaults advance
  from rendered gateway wall time each time the dialog opens.
- Keep `/records` form field names and `data-*` hooks stable. The server
  derives intake Start, validates options/durations and owns midnight rules;
  browser validation is an additional convenience. Native dialog supplies
  modal focus behavior; Cancel, Escape and backdrop dismiss it.
- Counters tick every second. `/api/state` polls every 30 seconds, on load,
  focus and becoming visible; it refreshes **Milk state only** and corrects
  clock offset from `server_epoch`. Failed fetches keep rendered state for
  the next retry. Other records/activity states still need page reload.
- Due feeding uses amber styling and translated reminder text; the web
  reminder no longer flashes. Firmware flashing is a separate contract.
- Daily timelines are flat lists without tables or checkboxes. Dates and
  displayed event times descend: intake and built-in points use End; Sleep
  and other sessions use Start. Every date starts expanded; fold buttons
  maintain `aria-expanded` and hide their list. Summaries show counts/intake
  and completed sleep duration; only present activities appear. Fold state
  is not stored across reloads.
- Each timeline entry is a native button with time, decorative activity icon,
  label, amount or duration, and escaped notes. It opens `#edit-record-dialog`.
  Save posts one hidden `record_id` and the existing `*_ID` fields to
  `/records/save`; confirmed Delete posts to `/records/delete`, bypassing
  edit validation. Custom/deleted activity names remain selectable. Intake
  Start is read-only; End is editable; ml/g follows the activity. Exact-second
  field values preserve midnight boundaries on notes-only saves.
- Day notes are separate from entry notes: the day-note button opens its own
  dialog posting `day_note_DATE` to `/records/save`; blank clears it. Existing
  day notes appear as text. Both editor forms fetch then reload the current
  page on success; failed saves keep the dialog and entered values for retry.
  Duplicate submits are guarded while saving. Escape, Cancel and backdrop
  dismiss idle dialogs. Dates/page count is server-owned; empty journal has
  a direct Milk dialog action.
- CSS breakpoints at 1050/900/600 px adapt spacing/cards; <=600 px timeline
  spacing narrows and form fields use 16 px text. Responsive
  controls, visible focus and reduced-motion rules live in `style.css`.
- Configuration posts activity names/timed flags, Poopoo/Supplement option
  lists, default language and settings to `/config`. Built-in intake names
  stay locked; deleted option sets use presence markers to preserve intent.

## Dependencies and Boundaries

[API](gateway-api.md) supplies `ui_home` context and every mutation endpoint;
read it when changing field names, context, response handling or timestamps.
[Storage](gateway-storage.md) owns configuration/options and canonical
activity normalization; read it when changing built-in behavior. Templates
never open a database. Treat Jinja escaping, JSON serialization and DOM
text insertion as trust boundaries for record notes/custom labels.

## Change Guide

| Change trigger | Inspect / extend | Required docs / checks |
| --- | --- | --- |
| Layout / icons / breakpoints | Templates, icon macro, CSS | Empty/populated EN/ZH at phone/tablet/desktop; keyboard/focus and long labels. |
| Dialog / record edits | Mode toggles, validators, handlers | Six default activity flows; amount units, popup save/delete, day notes, exact timestamps; API owner. |
| Timer / reminder | State polling, timer formatting, I18N order | Chinese units, remote feeding update, due/disabled alerts, recovery. |
| Settings / localization | Config controls, translation maps | Add/remove custom activities/options, save/reload and cookie/default precedence. |

## Verification

Run root syntax check, then the disposable gateway command in
[API Verification](gateway-api.md#verification). Open `http://127.0.0.1:8080/`
in a current browser. There is no frontend build/lint command or committed
browser suite. Required behavior checks for UI edits:

1. At 360, 390, 768 and 1440 px, render empty and populated logs in EN/ZH:
   no horizontal page overflow, clipped controls or console errors.
2. Save all six quick-log modes, tap timeline entries to edit or delete,
   save/clear entry and day notes, and change language/config/options. Verify
   only the selected entry mutates; timestamps, totals and ml/g survive reload.
   Check displayed-time sorting, exact midnight seconds, removed custom types,
   cancelled dialogs/deletions, invalid saves and fetch failure/retry.
3. Exercise custom timed activity start/stop and remote Milk state update;
   counters retain localized units. Test due Milk versus disabled alerts.
   Start Sleep with an adjusted Start, cancel/reopen, reload and stop it;
   Start stays editable in its popup and End stays blank while open.
   Check cross-midnight split on stop and preservation past the timer cap.
4. Navigate tabs/dialog/folds by keyboard; observe focus and ARIA state.
   Check long custom names and responsive labels; reduced-motion mode
   suppresses decorative animation.

Local Chromium checks passed the viewport/language matrix and six activity,
record edit/note/config/delete, custom-timer, empty/long-name, keyboard,
Milk-state/alert and reduced-motion flows.
No Safari/iOS or physical-device browser result is claimed. A screenshot
alone cannot establish submission/persistence or keyboard behavior.

## Known Gaps

No push channel; only Milk state refreshes without reload. No persisted
fold state or unsaved-edit recovery. JS/native dialog is required for the
normal quick-log flow; older-browser fallback is incomplete. Chinese units
must remain initialized before timer closures are created. Broader assistive
technology and Safari/iOS checks remain unverified. UI source and browser
checks, not the old single-640px layout description, define current behavior.
