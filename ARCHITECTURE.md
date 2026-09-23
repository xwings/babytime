---
eatmycode_version: "2.0.0"
---
# babytime Architecture

## Read First

Before planning code changes or reviewing code, read
[Agent Rules](ARCHITECTURE/AGENT_RULES.md). Follow the Task Index to the
owning module and read pages whose **Read when** trigger matches the task.
Load partner modules only for affected boundaries; never load the entire
ARCHITECTURE directory. Reuse unchanged pages already read in this session.
Check claims against source, configuration, and tests; they remain
authoritative. If a route or fact is missing or stale, inspect source and
repair the affected docs. For broad changes, work through owners in batches
and retain cross-owner constraints and verification evidence.

## Project Snapshot

| Fact | Value and evidence |
| --- | --- |
| Purpose | Baby activity tracker: ESP32 records completed feeds; optional gateway owns the durable log, browser editor and HTTP client integration. Entry points: `firmware/src/main.cpp`, `gateway/app/main.py`, `skill/scripts/babytime.py`. |
| Gateway | Python; declared image Python 3.12 in [Dockerfile](gateway/Dockerfile). FastAPI 0.115.5, uvicorn 0.32.1, Jinja2 3.1.4, Pydantic 2.10.3, multipart 0.0.18 pinned in [requirements](gateway/requirements.txt); SQLite via stdlib. |
| Firmware | Arduino C++/FreeRTOS through PlatformIO + pioarduino; compiler/standard selected by the platform, whose `stable` URL is unpinned. [platformio.ini](firmware/platformio.ini) selects DNESP32S3B or ESP32-P4-7B; P4 display/input remain stubs. |
| Browser / CLI | Jinja HTML, CSS, vanilla JavaScript; no frontend build tool. Stdlib HTTP CLI uses Python 3.10+ syntax; no broader compatibility matrix. |
| Scope | No implemented audio capture or notification service. P4 hardware bring-up remains pending; compiling a stub does not establish board support. |

## System Design

`HAL → firmware app ↔ HTTP gateway → SQLite records + JSON settings`;
`browser / skill client → same gateway`. Firmware owns an eight-record RAM
cache and pending queue; the gateway owns durable records and day notes.
`main.py` coordinates HTTP, auth and time normalization; storage does not
import routes. Its lifespan starts one scheduler task.

Epoch seconds are the wire/storage format. Gateway-local time controls
calendar grouping. Milk/Solid food end-time entries derive Start from
`auto_stop_minutes`; completed sleep splits at midnight and other completed
spans clamp to their first day (`main._segments`, `util.midnight_segments`).
Legacy open records remain compatible. Token/trusted-network checks guard
application routes; proxy trust is resolved by the app, so uvicorn uses
`--no-proxy-headers`. Read the API owner before changing auth or timestamps,
and firmware owners before changing state payloads.

## Code Conventions

| Area | Observed / required evidence |
| --- | --- |
| Style | Observed Python four spaces, snake_case functions, typed boundaries and relative app imports (`gateway/app/config.py`); firmware two spaces, PascalCase types, camelCase functions (`hal/hal.h`). No configured formatter, linter, type checker or CI. |
| Errors / design | HTTP validation uses `HTTPException`; storage uses explicit SQL and process locks. Firmware uses HAL interfaces and Serial diagnostics; scheduler prints errors. Follow each owner's local patterns. |
| UI | Labels use `i18n.t` and activity-label helpers; form names, DOM hooks and JSON field identifiers are contracts. Keep EN/ZH entries paired. |
| Local/generated files | `.pio`, Python caches and private firmware config are not source. Never copy credentials from ignored `firmware/include/config*.h`; the tracked example defines the public configuration surface. Missing tracked base-header setup is documented in its owner. |

## Verification

| Change/check | Command and working directory | Prerequisites / pass evidence |
| --- | --- | --- |
| Gateway setup | `python3 -m venv .venv`, then `.venv/bin/pip install -r requirements.txt` in `gateway/` | Python 3.12 image baseline; dependencies installed. |
| Python syntax | `python3 -m compileall -q gateway/app skill/scripts` at root | Exit 0 proves parsing, not behavior. |
| Gateway record tests | `PYTHONPATH=gateway gateway/.venv/bin/python -m unittest discover -s gateway/tests -v` at root | Gateway dependencies; disposable SQLite and controlled clock; Sleep and timeline edits. |
| Firmware build | `make build DEVICE=dnesp32s3b`; `make build DEVICE=esp32p4_7b` at root | PlatformIO, toolchain downloads and local `config.h`; each reports SUCCESS. Override `PIO` if needed. |
| Runtime / UI / storage | Owner Verification sections below | Disposable state; API/client, browser and hardware checks prove different behavior. |

Gateway records have a committed unittest suite; no CI exists. No lint/type-check command is
configured. Hardware behavior and fresh-clone firmware builds are not
certified; see owning gaps. Root [Makefile](Makefile) is firmware-only.

## Task Index

| Source paths / task trigger | Responsibility | Read next |
| --- | --- | --- |
| `firmware/src/{main.cpp,state.h,views.*}`, `firmware/include/config*`; state, views, HTTP/NTP | Firmware application and private configuration | [Firmware app](ARCHITECTURE/modules/firmware-app.md) |
| `firmware/src/hal/`, `firmware/{platformio.ini,partitions.csv}`, `Makefile`; boards, pins, builds | Hardware and toolchain | [Firmware HAL](ARCHITECTURE/modules/firmware-hal.md) |
| `gateway/app/{main.py,util.py}`, `gateway/{requirements.txt,Dockerfile,docker-compose.yml}`, `skill/`; routes, auth, time, HTTP client | Gateway API and client compatibility | [Gateway API](ARCHITECTURE/modules/gateway-api.md) |
| `gateway/app/{db.py,config.py}`; schema, settings, migrations | Persistence and configuration | [Gateway storage](ARCHITECTURE/modules/gateway-storage.md) |
| `gateway/app/scheduler.py`; background auto-stop | Scheduler | [Gateway scheduler](ARCHITECTURE/modules/gateway-scheduler.md) |
| `gateway/app/{templates/,static/,i18n.py}`; layout, controls, translation | Browser UI | [Gateway UI](ARCHITECTURE/modules/gateway-ui.md) |
