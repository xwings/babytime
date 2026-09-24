---
eatmycode_version: "2.1.0"
---
# babytime Architecture

Generated with [eatmycode](https://github.com/xwings/eatmycode).

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
| Purpose | Baby activity tracker: ESP32 records completed feeds; optional gateway owns the durable log, browser editor and HTTP client. Entry points: `firmware/src/main.cpp`, `gateway/app/main.py`, `skill/scripts/babytime.py`. |
| Gateway | Python; image Python 3.12 in [Dockerfile](gateway/Dockerfile), tests pass on local 3.13. FastAPI 0.115.5, uvicorn 0.32.1, Jinja2 3.1.4, Pydantic 2.10.3, multipart 0.0.18 pinned in [requirements](gateway/requirements.txt); SQLite via stdlib. |
| Firmware | Arduino C++/FreeRTOS via PlatformIO + pioarduino; compiler/standard come from the unpinned `stable` platform. [platformio.ini](firmware/platformio.ini) selects DNESP32S3B or ESP32-P4-7B; P4 display/input are stubs. |
| Browser / CLI | Jinja HTML, CSS, vanilla JavaScript; no frontend build tool. Stdlib HTTP CLI uses Python 3.10+ syntax; no wider matrix. |
| Scope | No audio capture or notification service. P4 hardware bring-up is pending; compiling a stub does not establish board support. |

## System Design

`HAL → firmware app ↔ HTTP gateway → SQLite records + JSON settings`;
`browser / skill client → same gateway`. Firmware owns an eight-record RAM
cache and pending queue; the gateway owns durable records and day notes.
`main.py` coordinates HTTP, auth and time normalization; storage does not
import routes. Its lifespan starts one scheduler task.

Epoch seconds are the wire/storage format; saved gateway `timezone`, not
`TZ`, controls calendar grouping. Milk/Food entries (except Water) are End times
with Start derived from `auto_stop_minutes`; completed sleep splits at
midnight and other completed spans clamp to their first day
(`main._segments`, `util.midnight_segments`); Water is a point. Legacy open records stay
compatible. Token/trusted-network checks guard all application routes;
proxy trust is resolved by the app, so uvicorn runs `--no-proxy-headers`.
Read the API owner before changing auth or timestamps, and firmware owners
before changing state payloads.

## Code Conventions

| Area | Observed / required evidence |
| --- | --- |
| Style | Observed Python four spaces, snake_case, typed boundaries, relative app imports (`gateway/app/config.py`); firmware two spaces, PascalCase types, camelCase functions (`hal/hal.h`). No formatter, linter, type checker or CI is configured. |
| Errors / design | HTTP validation uses `HTTPException`; storage uses explicit SQL and a process lock. Firmware uses HAL interfaces and Serial diagnostics; the scheduler prints errors. Follow each owner's local patterns. |
| UI | Labels use `i18n.t` and activity-label helpers; form names, DOM hooks and JSON field identifiers are contracts. Keep EN/ZH entries paired. |
| Local files | `.pio`, Python caches, `gateway/.venv` and private firmware config are not source. Never copy credentials from ignored `firmware/include/config*.h`; the tracked example defines the public surface. |

## Verification

| Change/check | Command and working directory | Prerequisites / pass evidence |
| --- | --- | --- |
| Gateway setup | `python3 -m venv .venv`, then `.venv/bin/pip install -r requirements.txt` in `gateway/` | Python 3.12+; pinned dependencies installed. |
| Python syntax | `python3 -m compileall -q gateway/app skill/scripts` at root | Exit 0 proves parsing only. |
| Gateway tests | `PYTHONPATH=gateway gateway/.venv/bin/python -m unittest discover -s gateway/tests -v` at root | 17 cases; disposable state. |
| Firmware build | `make build DEVICE=dnesp32s3b`; `make build DEVICE=esp32p4_7b` at root | PlatformIO, toolchain downloads and a local `config.h`; each reports SUCCESS. Override `PIO` if needed. |
| Runtime / UI / storage | Owner Verification sections and their topics | Disposable state; API/CLI smoke, browser and hardware checks prove different behavior. |

No CI, lint or type check exists. Hardware behavior and fresh-clone
firmware builds are uncertified; PlatformIO was unavailable in the latest
refresh. Root [Makefile](Makefile) is firmware-only.

## Task Index

| Source paths / task trigger | Responsibility | Read next |
| --- | --- | --- |
| `firmware/src/{main.cpp,state.h,views.*}`, `firmware/include/config*`; state, views, HTTP/NTP | Firmware application and private configuration | [Firmware app](ARCHITECTURE/modules/firmware-app.md) |
| `firmware/src/hal/`, `firmware/{platformio.ini,partitions.csv}`, `Makefile`; boards, pins, builds | Hardware and toolchain | [Firmware HAL](ARCHITECTURE/modules/firmware-hal.md) |
| `gateway/app/{main.py,util.py}`, `gateway/{requirements.txt,Dockerfile,docker-compose.yml}`, `skill/`, `gateway/tests/`; routes, auth, time, HTTP client | Gateway API and client compatibility | [Gateway API](ARCHITECTURE/modules/gateway-api.md) |
| `gateway/app/{db.py,config.py}`; schema, settings, migrations | Persistence and configuration | [Gateway storage](ARCHITECTURE/modules/gateway-storage.md) |
| `gateway/app/scheduler.py`; background auto-stop | Scheduler | [Gateway scheduler](ARCHITECTURE/modules/gateway-scheduler.md) |
| `gateway/app/{templates/,static/,i18n.py}`; layout, controls, translation | Browser UI | [Gateway UI](ARCHITECTURE/modules/gateway-ui.md) |
