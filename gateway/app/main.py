import asyncio
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import (
    Depends,
    FastAPI,
    Form,
    Header,
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


app = FastAPI(title="babytime gateway", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def check_token(authorization: Optional[str] = Header(None)) -> None:
    if not GATEWAY_TOKEN:
        return
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if token != GATEWAY_TOKEN:
        raise HTTPException(status_code=403, detail="invalid token")


def state_payload() -> dict:
    return {
        "active": db.get_active("feeding"),
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


@app.post("/api/events", dependencies=[Depends(check_token)])
async def api_post_event(event: EventIn):
    if event.type not in ("start", "stop"):
        raise HTTPException(400, "type must be 'start' or 'stop'")
    ts = event.timestamp_epoch or int(time.time())
    if event.type == "start":
        if db.get_active(event.activity) is None:
            db.create_record(
                start_epoch=ts, activity=event.activity, device_id=event.device_id
            )
    else:
        db.stop_active(stop_epoch=ts, activity=event.activity)
    return state_payload()


@app.get("/api/state", dependencies=[Depends(check_token)])
async def api_get_state():
    return state_payload()


@app.get("/api/records", dependencies=[Depends(check_token)])
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


@app.post("/api/records", dependencies=[Depends(check_token)])
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


@app.patch("/api/records/{rid}", dependencies=[Depends(check_token)])
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


@app.delete("/api/records/{rid}", dependencies=[Depends(check_token)])
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


@app.get("/api/day_notes", dependencies=[Depends(check_token)])
async def api_get_day_notes():
    return db.get_day_notes()


@app.put("/api/day_notes/{date}", dependencies=[Depends(check_token)])
async def api_put_day_note(date: str, body: DayNoteIn):
    date = _valid_date(date)
    db.set_day_note(date, body.note)
    return {"date": date, "note": (body.note or "").strip()}


@app.get("/api/config", dependencies=[Depends(check_token)])
async def api_get_config():
    return config.load()


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
    lang = i18n.read_lang(request)
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
        db.create_record(start_epoch=ts, activity=activity, device_id="web")
    return RedirectResponse("/", status_code=303)


@app.post("/records")
async def ui_create(
    date: str = Form(...),
    start_time: str = Form(...),
    stop_time: str = Form(""),
    volume_ml: str = Form(""),
    activity: str = Form("feeding"),
):
    cfg = config.load()
    tz = cfg.get("timezone") or "UTC"
    start_epoch = combine_date_time(date, start_time, tz)
    if start_epoch is None:
        raise HTTPException(400, "date and start_time required")
    stop_epoch = combine_date_time(date, stop_time, tz) if stop_time.strip() else None
    if stop_epoch is not None and stop_epoch < start_epoch:
        stop_epoch += 86400  # session crossed midnight
    db.create_record(
        start_epoch=start_epoch,
        stop_epoch=stop_epoch,
        volume_ml=_feeding_volume(activity, volume_ml),
        activity=activity or "feeding",
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
