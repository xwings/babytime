import asyncio
import base64
import hmac
import ipaddress
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import (
    Depends,
    FastAPI,
    Form,
    HTTPException,
    Request,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from . import config, db, i18n, scheduler
from .util import zoneinfo

GATEWAY_TOKEN = os.environ.get("GATEWAY_TOKEN", "").strip()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def filter_localtime(epoch: Optional[int], tz_name: str = "UTC") -> str:
    if not epoch:
        return ""
    return datetime.fromtimestamp(int(epoch), tz=zoneinfo(tz_name)).strftime(
        "%Y-%m-%d %H:%M"
    )


def filter_localdate_input(epoch: Optional[int], tz_name: str = "UTC") -> str:
    if not epoch:
        return ""
    return datetime.fromtimestamp(int(epoch), tz=zoneinfo(tz_name)).strftime("%Y-%m-%d")


def filter_localtime_only(epoch: Optional[int], tz_name: str = "UTC") -> str:
    if not epoch:
        return ""
    return datetime.fromtimestamp(int(epoch), tz=zoneinfo(tz_name)).strftime("%H:%M")


def filter_duration(start: Optional[int], stop: Optional[int]) -> str:
    if not start or not stop:
        return ""
    d = int(stop) - int(start)
    if d < 0:
        d = 0
    if d >= 3600:
        return f"{d // 3600}h {(d % 3600) // 60}m"
    return f"{d // 60}m {d % 60}s"


templates.env.filters["localtime"] = filter_localtime
templates.env.filters["localdate_input"] = filter_localdate_input
templates.env.filters["localtime_only"] = filter_localtime_only
templates.env.filters["duration"] = filter_duration


def combine_date_time(date_str: str, time_str: str, tz_name: str = "UTC") -> Optional[int]:
    if not date_str or not time_str:
        return None
    date_str = date_str.strip()
    time_str = time_str.strip()
    if not date_str or not time_str:
        return None
    fmt = "%Y-%m-%dT%H:%M:%S" if time_str.count(":") >= 2 else "%Y-%m-%dT%H:%M"
    dt = datetime.strptime(f"{date_str}T{time_str}", fmt).replace(tzinfo=zoneinfo(tz_name))
    return int(dt.timestamp())


def _to_epoch(value, tz_name: str = "UTC") -> Optional[int]:
    """Coerce a JSON timestamp field to epoch seconds.

    Accepts an int/float epoch, an all-digit string, or an ISO-ish datetime
    (`YYYY-MM-DD HH:MM[:SS]`, optionally with `T`, a UTC offset, or `Z`). A
    naive string is read in the gateway's configured timezone, so agents can
    send local wall-clock times without knowing the offset."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    s = str(value).strip()
    if not s:
        return None
    if s.lstrip("-").isdigit():
        return int(s)
    try:
        dt = datetime.fromisoformat(s.replace(" ", "T").replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(400, f"unparseable datetime: {value!r}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=zoneinfo(tz_name))
    return int(dt.timestamp())


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    config.migrate_from(db.legacy_config_rows)
    task = asyncio.create_task(scheduler.scheduler_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# Browsers re-prompt for credentials on a 401 carrying this challenge; the
# API/skill/firmware ignore it and just resend their Bearer header.
_AUTH_CHALLENGE = {"WWW-Authenticate": 'Basic realm="babytime"'}


def _effective_client_ip(request: Request, cfg: dict):
    """The IP the trust decision should key on.

    Normally the direct peer (`request.client.host`). When that peer is a
    configured reverse proxy (`trusted_proxies`), walk back through the
    `X-Forwarded-For` chain — skipping further trusted-proxy hops — to the
    real client the proxy is fronting. `X-Forwarded-For` is ignored entirely
    when the peer isn't a known proxy, so a direct client can't spoof it."""
    client = request.client
    if client is None:
        return None
    proxies = config.trusted_proxies(cfg)
    # Connection side last: the forwarded list is client-most-first, the
    # actual peer is appended on the right.
    forwarded = request.headers.get("X-Forwarded-For", "")
    chain = [h.strip() for h in forwarded.split(",") if h.strip()] + [client.host]
    for hop in reversed(chain):
        try:
            ip = ipaddress.ip_address(hop)
        except ValueError:
            continue
        if any(ip in net for net in proxies):
            continue  # a proxy hop — keep looking inward for the real client
        return ip
    return None


def _client_is_trusted(request: Request, cfg: dict) -> bool:
    """True when the effective client IP falls inside a `trusted_networks`
    block. Trusted clients (the home LAN by default) skip auth entirely."""
    ip = _effective_client_ip(request, cfg)
    if ip is None:
        return False
    return any(ip in net for net in config.trusted_networks(cfg))


def _presented_token(request: Request) -> Optional[str]:
    """Pull the gateway token out of the Authorization header, whether it
    arrived as a machine `Bearer <token>` or a browser `Basic <user:token>`
    (the username is ignored; the password is the token)."""
    header = request.headers.get("Authorization")
    if not header:
        return None
    scheme, _, rest = header.partition(" ")
    scheme = scheme.lower()
    if scheme == "bearer":
        return rest.strip()
    if scheme == "basic":
        try:
            decoded = base64.b64decode(rest.strip()).decode("utf-8", "replace")
        except (ValueError, UnicodeDecodeError):
            return None
        _, _, password = decoded.partition(":")
        return password
    return None


def require_auth(request: Request) -> None:
    """Gate every route: trusted-network clients pass freely, everyone else
    must present the gateway token (Bearer for machines, Basic password for
    browsers). A missing token set on the server leaves the gateway open."""
    if not GATEWAY_TOKEN:
        return
    if _client_is_trusted(request, config.load()):
        return
    presented = _presented_token(request)
    if presented and hmac.compare_digest(presented, GATEWAY_TOKEN):
        return
    raise HTTPException(status_code=401, detail="authentication required", headers=_AUTH_CHALLENGE)


# One global gate covers the JSON API and the browser UI alike; the mounted
# /static sub-app is intentionally left open (CSS only, no secrets).
app = FastAPI(
    title="babytime gateway",
    lifespan=lifespan,
    dependencies=[Depends(require_auth)],
)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def state_payload() -> dict:
    tz = zoneinfo(config.load().get("timezone") or "UTC")
    day_start = datetime.now(tz=tz).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = (day_start + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    today = db.feeding_totals(int(day_start.timestamp()), int(day_end.timestamp()))
    last_feeding = db.list_records(limit=1, activity="feeding")
    return {
        "active": db.get_active("feeding"),
        "last_feeding": last_feeding[0] if last_feeding else None,
        "today_feeds": today["feeds"],
        "today_ml": today["ml"],
        "history": db.list_records(limit=8),
        "server_epoch": int(time.time()),
    }


# ---------------------------------------------------------------------------
# Device-facing API
# ---------------------------------------------------------------------------


class EventIn(BaseModel):
    type: str
    device_id: str = ""
    activity: str = "feeding"
    timestamp_epoch: Optional[int] = None


@app.post("/api/events")
async def api_post_event(event: EventIn):
    if event.type not in ("start", "stop"):
        raise HTTPException(400, "type must be 'start' or 'stop'")
    ts = event.timestamp_epoch or int(time.time())
    if event.type == "start":
        if db.get_active(event.activity) is None:
            cfg = config.load()
            db.create_record(
                start_epoch=ts,
                activity=event.activity,
                device_id=event.device_id,
                volume_ml=_feeding_volume(event.activity, cfg.get("default_volume_ml")),
            )
    else:
        db.stop_active(stop_epoch=ts, activity=event.activity)
    return state_payload()


@app.get("/api/state")
async def api_get_state():
    return state_payload()


@app.get("/api/records")
async def api_list_records(limit: int = 100):
    return db.list_records(limit=limit)


class RecordIn(BaseModel):
    start: Optional[int | str] = None
    stop: Optional[int | str] = None
    volume_ml: Optional[int] = None
    activity: str = "feeding"
    notes: Optional[str] = None
    device_id: str = "agent"


def _require_record(rid: int) -> dict:
    rows = db.list_records(ids=[rid])
    if not rows:
        raise HTTPException(404, f"record {rid} not found")
    return rows[0]


@app.post("/api/records")
async def api_create_record(body: RecordIn):
    tz = config.load().get("timezone") or "UTC"
    start = _to_epoch(body.start, tz)
    if start is None:
        raise HTTPException(400, "start is required")
    stop = _to_epoch(body.stop, tz)
    if stop is not None and stop < start:
        stop += 86400  # session crossed midnight
    rid = db.create_record(
        start_epoch=start,
        stop_epoch=stop,
        volume_ml=_feeding_volume(body.activity, body.volume_ml),
        activity=body.activity or "feeding",
        notes=body.notes or None,
        device_id=body.device_id or "agent",
    )
    return _require_record(rid)


@app.patch("/api/records/{rid}")
async def api_update_record(rid: int, body: RecordIn):
    existing = _require_record(rid)
    tz = config.load().get("timezone") or "UTC"
    provided = body.model_dump(exclude_unset=True)

    fields: dict = {}
    if "start" in provided:
        fields["start_epoch"] = _to_epoch(provided["start"], tz)
    if "stop" in provided:
        fields["stop_epoch"] = _to_epoch(provided["stop"], tz)
    if "notes" in provided:
        fields["notes"] = provided["notes"] or None
    if "device_id" in provided:
        fields["device_id"] = provided["device_id"] or ""
    if "activity" in provided:
        fields["activity"] = provided["activity"] or "feeding"

    effective_activity = provided.get("activity") or existing["activity"]
    if effective_activity != "feeding":
        if existing["volume_ml"] is not None or "volume_ml" in provided:
            fields["volume_ml"] = None  # non-feeding never carries volume
    elif "volume_ml" in provided:
        fields["volume_ml"] = _feeding_volume(effective_activity, provided["volume_ml"])

    db.update_record(rid, **fields)
    return _require_record(rid)


@app.delete("/api/records/{rid}")
async def api_delete_record(rid: int):
    _require_record(rid)
    db.delete_record(rid)
    return {"ok": True, "deleted": rid}


class DayNoteIn(BaseModel):
    note: str = ""


def _valid_date(date: str) -> str:
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, f"date must be YYYY-MM-DD, got {date!r}")
    return date


@app.get("/api/day_notes")
async def api_get_day_notes():
    return db.get_day_notes()


@app.put("/api/day_notes/{date}")
async def api_put_day_note(date: str, body: DayNoteIn):
    date = _valid_date(date)
    db.set_day_note(date, body.note)
    return {"date": date, "note": (body.note or "").strip()}


@app.get("/api/config")
async def api_get_config():
    return config.load()


@app.get("/api/activities")
async def api_get_activities():
    """The configured activity types an agent may write, each flagged
    `timed` (start->stop session) or instant (single timestamp)."""
    cfg = config.load()
    timed = config.timed_activities(cfg)
    return [{"activity": a, "timed": a in timed} for a in config.activity_list(cfg)]


# ---------------------------------------------------------------------------
# Web UI
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def ui_home(
    request: Request,
    page: int = 1,
):
    cfg = config.load()
    try:
        dates_per_page = int(cfg.get("ui_show_count") or "10")
    except ValueError:
        dates_per_page = 10
    if dates_per_page < 1:
        dates_per_page = 10
    tz_name = cfg.get("timezone") or "UTC"
    tz = zoneinfo(tz_name)

    all_records = db.list_records()
    by_date: dict[str, list] = {}
    date_order: list[str] = []
    for r in all_records:
        d = datetime.fromtimestamp(int(r["start_epoch"]), tz=tz).strftime("%Y-%m-%d")
        if d not in by_date:
            by_date[d] = []
            date_order.append(d)
        by_date[d].append(r)
    total_dates = len(date_order)
    total_pages = max(1, (total_dates + dates_per_page - 1) // dates_per_page)
    if page < 1:
        page = 1
    if page > total_pages:
        page = total_pages
    start = (page - 1) * dates_per_page
    page_dates = date_order[start:start + dates_per_page]
    day_notes = db.get_day_notes(page_dates)
    groups = [
        {
            "date": d,
            "records": by_date[d],
            "ml_count": sum(1 for r in by_date[d] if r["volume_ml"]),
            "total_ml": sum((r["volume_ml"] or 0) for r in by_date[d]),
            "note": day_notes.get(d, ""),
        }
        for d in page_dates
    ]

    now_epoch = int(time.time())
    auto_check_cutoff = now_epoch - 86400

    activities = config.activity_list(cfg)
    timed = config.timed_activities(cfg)
    active_map = {a: s for a in activities if a in timed and (s := db.get_active(a))}
    last_fed = next(
        (r for r in all_records
         if r.get("stop_epoch") and r["activity"] == "feeding"),
        None,
    )

    now = datetime.now(tz=tz)
    lang = i18n.read_lang(request, cfg.get("default_language"))
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "lang": lang,
            "html_lang": i18n.html_lang_attr(lang),
            "t": (lambda key, **kw: i18n.t(key, lang, **kw)),
            "al": (lambda name: i18n.activity_label(name, lang)),
            "groups": groups,
            "activities": activities,
            "languages": i18n.language_options(),
            "timed": sorted(timed),
            "active_map": active_map,
            "last_fed": last_fed,
            "now_epoch": now_epoch,
            "config": cfg,
            "tz": tz_name,
            "now_date": now.strftime("%Y-%m-%d"),
            "now_time": now.strftime("%H:%M"),
            "page": page,
            "total_pages": total_pages,
            "total_records": len(all_records),
            "total_dates": total_dates,
            "dates_per_page": dates_per_page,
            "auto_check_cutoff": auto_check_cutoff,
            "config_keys_simple": [
                "auto_stop_minutes",
                "default_volume_ml",
                "timezone",
                "ui_show_count",
                "trusted_networks",
                "trusted_proxies",
            ],
        },
    )


def _feeding_volume(activity: str, raw_ml) -> Optional[int]:
    """Volume is only meaningful for feeding; other activities store none.

    Accepts the raw form string or an int/None (JSON API), so the rule has
    a single definition shared by the web UI and the JSON endpoints."""
    if activity != "feeding" or raw_ml is None:
        return None
    s = str(raw_ml).strip()
    return int(s) if s else None


@app.post("/ui/activity")
async def ui_activity_toggle(activity: str = Form("feeding")):
    ts = int(time.time())
    if activity not in config.timed_activities(config.load()):
        # Instant event: log a single closed timestamp (start == stop) so it
        # never looks like an open session to the device, scheduler, or UI.
        db.create_record(start_epoch=ts, stop_epoch=ts, activity=activity, device_id="web")
    elif db.get_active(activity):
        db.stop_active(stop_epoch=ts, activity=activity)
    else:
        db.create_record(
            start_epoch=ts,
            activity=activity,
            device_id="web",
            volume_ml=_feeding_volume(activity, config.load().get("default_volume_ml")),
        )
    return RedirectResponse("/", status_code=303)


@app.post("/records")
async def ui_create(
    date: str = Form(...),
    start_time: str = Form(...),
    stop_time: str = Form(""),
    volume_ml: str = Form(""),
    activity: str = Form("feeding"),
    notes: str = Form(""),
):
    cfg = config.load()
    tz = cfg.get("timezone") or "UTC"
    start_epoch = combine_date_time(date, start_time, tz)
    if start_epoch is None:
        raise HTTPException(400, "date and start_time required")
    activity = activity or "feeding"
    if activity not in config.timed_activities(cfg):
        stop_epoch = start_epoch  # instant event: a single closed timestamp
    else:
        stop_epoch = combine_date_time(date, stop_time, tz) if stop_time.strip() else None
        if stop_epoch is not None and stop_epoch < start_epoch:
            stop_epoch += 86400  # session crossed midnight
    db.create_record(
        start_epoch=start_epoch,
        stop_epoch=stop_epoch,
        volume_ml=_feeding_volume(activity, volume_ml),
        activity=activity,
        notes=notes.strip() or None,
    )
    return RedirectResponse("/", status_code=303)


@app.post("/records/save")
async def ui_bulk_save(request: Request):
    cfg = config.load()
    tz = cfg.get("timezone") or "UTC"
    form = await request.form()
    timed = config.timed_activities(cfg)
    rids = [int(v) for v in form.getlist("record_id") if str(v).isdigit()]
    for rid in rids:
        date = (form.get(f"date_{rid}") or "").strip()
        start_time = (form.get(f"start_time_{rid}") or "").strip()
        stop_time = (form.get(f"stop_time_{rid}") or "").strip()
        if not date or not start_time:
            continue
        start_epoch = combine_date_time(date, start_time, tz)
        activity = (form.get(f"activity_{rid}") or "feeding").strip() or "feeding"
        if activity not in timed:
            stop_epoch = start_epoch  # instant event has no editable stop
        else:
            stop_epoch = combine_date_time(date, stop_time, tz) if stop_time else None
            if stop_epoch is not None and stop_epoch < start_epoch:
                stop_epoch += 86400  # session crossed midnight
        volume_ml = form.get(f"volume_ml_{rid}") or ""
        db.update_record(
            rid,
            start_epoch=start_epoch,
            stop_epoch=stop_epoch,
            volume_ml=_feeding_volume(activity, volume_ml),
            activity=activity,
            notes=(form.get(f"notes_{rid}") or "").strip() or None,
        )
    for key, value in form.multi_items():
        if key.startswith("day_note_"):
            db.set_day_note(key[len("day_note_"):], str(value))
    return RedirectResponse("/", status_code=303)


@app.post("/records/delete")
async def ui_bulk_delete(request: Request):
    form = await request.form()
    rids = [int(v) for v in form.getlist("record_id") if str(v).isdigit()]
    for rid in rids:
        db.delete_record(rid)
    return RedirectResponse("/", status_code=303)


@app.post("/config")
async def ui_save_config(request: Request):
    form = await request.form()
    items: dict = {}
    rows: list[tuple[str, str]] = []  # (row index, activity name) in form order
    timed_rows: set[str] = set()
    for key, value in form.multi_items():
        if key.startswith("activity_name_"):
            rows.append((key[len("activity_name_"):], str(value).strip()))
        elif key.startswith("activity_timed_"):
            timed_rows.add(key[len("activity_timed_"):])
        else:
            items[key] = str(value)
    if rows:
        # Rebuild the two activity lists from the per-row name + timed toggle.
        # config.activity_list / timed_activities re-force 'feeding', so the
        # feeding row (read-only name, disabled checkbox) need not round-trip.
        items["activity_types"] = ",".join(name for _, name in rows if name)
        items["timed_activities"] = ",".join(
            name for ri, name in rows if name and ri in timed_rows
        )
    config.update(items)
    return RedirectResponse("/#config", status_code=303)


@app.get("/lang/{code}")
async def ui_set_lang(code: str, request: Request):
    target = i18n.normalize(code)
    dest = request.headers.get("referer") or "/"
    resp = RedirectResponse(dest, status_code=303)
    resp.set_cookie(
        i18n.LANG_COOKIE,
        target,
        max_age=i18n.COOKIE_MAX_AGE,
        samesite="lax",
        httponly=False,
    )
    return resp
