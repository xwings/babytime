import asyncio
import base64
import hmac
import ipaddress
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode

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
MAX_RECORD_DURATION_SECONDS = 30 * 60
MAX_SLEEP_DURATION_SECONDS = 24 * 60 * 60
_BROWSER_AUTH_COOKIE = "babytime_access"
_BROWSER_AUTH_MAX_AGE = 365 * 24 * 60 * 60
_BROWSER_AUTH_CONTEXT = b"babytime-browser-access-v1"

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
    if start is None or stop is None:
        return ""
    d = int(stop) - int(start)
    if d < 0:
        d = 0
    total_minutes = d // 60
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


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


def _normalize_stop_epoch(
    start_epoch: int,
    stop_epoch: Optional[int],
    activity: str = "",
) -> Optional[int]:
    if stop_epoch is None:
        return None
    if stop_epoch < start_epoch:
        stop_epoch += 86400  # session crossed midnight
    duration = stop_epoch - start_epoch
    max_seconds = (
        MAX_SLEEP_DURATION_SECONDS if activity == "sleep" else MAX_RECORD_DURATION_SECONDS
    )
    if duration > max_seconds:
        max_minutes = max_seconds // 60
        raise HTTPException(
            400,
            f"stop time must be within {max_minutes} minutes of start time",
        )
    return stop_epoch


_DURATION_HHMM_RE = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")


def _duration_hhmm_seconds(value: str) -> int:
    """Parse a positive sleep duration written as ``HH:MM``."""
    value = (value or "").strip()
    if not _DURATION_HHMM_RE.fullmatch(value):
        raise HTTPException(400, "duration must use HH:MM (for example, 08:30)")
    hours, minutes = (int(part) for part in value.split(":"))
    seconds = (hours * 60 + minutes) * 60
    if seconds <= 0:
        raise HTTPException(400, "duration must be greater than 00:00")
    return seconds


def _feeding_bounds(end_epoch: int, cfg: dict) -> tuple[int, int]:
    """Return the configured fixed-duration feeding ending at ``end_epoch``."""
    duration_seconds = config.feeding_duration_minutes(cfg) * 60
    return max(0, end_epoch - duration_seconds), end_epoch


def _poopoo_notes(
    cfg: dict,
    amount: str,
    color: str,
    texture: str,
    extra_notes: str,
) -> str:
    """Validate Poopoo selections and serialize them into record notes."""
    choices = config.poopoo_options(cfg)
    selected = {
        "Amount": ("amount", (amount or "").strip()),
        "Color": ("color", (color or "").strip()),
        "Texture": ("texture", (texture or "").strip()),
    }
    parts: list[str] = []
    for label, (group, value) in selected.items():
        allowed = choices[group]
        if (allowed and not value) or (value and value not in allowed):
            raise HTTPException(400, f"poopoo {group} selection is required")
        if value:
            parts.append(f"{label}: {value}")
    extra = (extra_notes or "").strip()
    if extra:
        parts.append(f"Extra notes: {extra}")
    return "; ".join(parts)


def _supplement_notes(cfg: dict, supplement_type: str, extra_notes: str = "") -> str:
    """Validate a Supplement choice and serialize it into record notes."""
    choice = (supplement_type or "").strip()
    allowed = config.supplement_options(cfg)
    if (allowed and not choice) or (choice and choice not in allowed):
        raise HTTPException(400, "supplement selection is required")
    parts = [f"Supplement: {choice}"] if choice else []
    extra = (extra_notes or "").strip()
    if extra:
        parts.append(f"Extra notes: {extra}")
    return "; ".join(parts)


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


def _browser_cookie_value() -> str:
    """Derive a browser credential without storing the raw API key.

    Changing GATEWAY_TOKEN automatically invalidates every existing browser
    session because it changes this value.
    """
    return hmac.new(
        GATEWAY_TOKEN.encode("utf-8"),
        _BROWSER_AUTH_CONTEXT,
        "sha256",
    ).hexdigest()


def _browser_cookie_is_valid(request: Request) -> bool:
    presented = request.cookies.get(_BROWSER_AUTH_COOKIE, "")
    return bool(
        GATEWAY_TOKEN
        and presented
        and hmac.compare_digest(presented, _browser_cookie_value())
    )


def _gateway_token_matches(presented: str) -> bool:
    """Constant-time token comparison that also handles non-ASCII input."""
    return bool(
        GATEWAY_TOKEN
        and hmac.compare_digest(
            presented.encode("utf-8"),
            GATEWAY_TOKEN.encode("utf-8"),
        )
    )


def _browser_link_key_is_valid(request: Request) -> bool:
    """Whether this is a valid browser landing link on the UI root."""
    if request.method != "GET" or request.url.path != "/":
        return False
    api_key = request.query_params.get("api")
    return api_key is not None and _gateway_token_matches(api_key)


def require_auth(request: Request) -> None:
    """Gate every route: trusted-network clients pass freely, everyone else
    must present the gateway token (Bearer/Basic) or a browser cookie issued
    by the API-key link. An unset server token leaves the gateway open."""
    if not GATEWAY_TOKEN:
        return
    if _client_is_trusted(request, config.load()):
        return
    presented = _presented_token(request)
    if presented and _gateway_token_matches(presented):
        return
    if _browser_cookie_is_valid(request):
        return
    if _browser_link_key_is_valid(request):
        return
    raise HTTPException(status_code=401, detail="authentication required", headers=_AUTH_CHALLENGE)


# One global gate covers the JSON API and the browser UI alike; the mounted
# /static sub-app is intentionally left open (CSS only, no secrets).
app = FastAPI(
    title="babytime gateway",
    lifespan=lifespan,
    dependencies=[Depends(require_auth)],
)


@app.middleware("http")
async def browser_api_key_link(request: Request, call_next):
    """Turn `/?api=<GATEWAY_TOKEN>` into a persistent browser login.

    Normal mode redirects to remove the secret. ``shortcut=1`` intentionally
    keeps it in the rendered URL for iOS Home Screen launchers with a separate
    cookie context. Both modes issue an HTTPS-only HMAC-derived cookie.
    """
    if _browser_link_key_is_valid(request):
        shortcut_mode = request.query_params.get("shortcut", "").lower() in {
            "1",
            "true",
            "yes",
        }
        if shortcut_mode:
            # iOS Home Screen can use a separate cookie context. Keep the API
            # key in this opt-in shortcut URL so every launch can authenticate
            # and refresh its own browser cookie.
            response = await call_next(request)
        else:
            clean_query = [
                (key, value)
                for key, value in request.query_params.multi_items()
                if key not in {"api", "shortcut"}
            ]
            target = request.url.path
            if clean_query:
                target += "?" + urlencode(clean_query)
            response = RedirectResponse(target, status_code=303)
        response.set_cookie(
            _BROWSER_AUTH_COOKIE,
            _browser_cookie_value(),
            max_age=_BROWSER_AUTH_MAX_AGE,
            path="/",
            secure=True,
            httponly=True,
            samesite="lax",
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response
    return await call_next(request)


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def _feeding_alert_payload(
    cfg: dict,
    active: Optional[dict],
    last_feeding: Optional[dict],
    now_epoch: Optional[int] = None,
) -> dict:
    threshold_minutes = config.feeding_alert_minutes(cfg)
    now_epoch = int(now_epoch or time.time())
    elapsed_seconds = 0
    due = False
    stop_epoch = last_feeding.get("stop_epoch") if last_feeding else None
    if threshold_minutes > 0 and active is None and stop_epoch:
        elapsed_seconds = max(0, now_epoch - int(stop_epoch))
        due = elapsed_seconds >= threshold_minutes * 60
    return {
        "due": due,
        "threshold_minutes": threshold_minutes,
        "elapsed_seconds": elapsed_seconds,
        "message": "Time to feed?",
    }


def state_payload() -> dict:
    cfg = config.load()
    tz = zoneinfo(cfg.get("timezone") or "UTC")
    day_start = datetime.now(tz=tz).replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = (day_start + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    today = db.feeding_totals(int(day_start.timestamp()), int(day_end.timestamp()))
    feeding_history = db.list_records(activity="feeding")
    active = db.get_active("feeding")
    last = next((r for r in feeding_history if r.get("stop_epoch")), None)
    server_epoch = int(time.time())
    return {
        "active": active,
        "last_feeding": last,
        "today_feeds": today["feeds"],
        "today_ml": today["ml"],
        "history": db.list_records(limit=8),
        "server_epoch": server_epoch,
        "feeding_duration_minutes": config.feeding_duration_minutes(cfg),
        "feeding_alert": _feeding_alert_payload(cfg, active, last, server_epoch),
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
    if event.type not in ("start", "stop", "log"):
        raise HTTPException(400, "type must be 'start', 'stop', or 'log'")
    ts = event.timestamp_epoch or int(time.time())
    cfg = config.load()
    activity = config.canonical_activity(event.activity) or "feeding"
    if event.type == "start":
        if db.get_active(activity) is None:
            db.create_record(
                start_epoch=ts,
                activity=activity,
                device_id=event.device_id,
                volume_ml=_feeding_volume(activity, cfg.get("default_volume_ml")),
            )
    elif event.type == "stop":
        if activity == "feeding":
            active = db.get_active(activity)
            if active:
                start_epoch, stop_epoch = _feeding_bounds(ts, cfg)
                db.update_record(
                    active["id"],
                    start_epoch=start_epoch,
                    stop_epoch=stop_epoch,
                )
        else:
            db.stop_active(stop_epoch=ts, activity=activity)
    else:
        # Current devices send one `log` event when a feed has finished. If
        # an older client left a session open, normalize it to the configured
        # duration too. For Feeding, the press is always End.
        active = db.get_active(activity)
        if activity == "feeding":
            start_epoch, stop_epoch = _feeding_bounds(ts, cfg)
            if active:
                db.update_record(
                    active["id"],
                    start_epoch=start_epoch,
                    stop_epoch=stop_epoch,
                )
            else:
                db.create_record(
                    start_epoch=start_epoch,
                    stop_epoch=stop_epoch,
                    activity=activity,
                    device_id=event.device_id,
                    volume_ml=_feeding_volume(activity, cfg.get("default_volume_ml")),
                )
        elif activity in {"poopoo", "supplement"}:
            # Every point-activity log is independent; do not close or reuse
            # an older open record.
            db.create_record(
                start_epoch=ts,
                stop_epoch=ts,
                activity=activity,
                device_id=event.device_id,
            )
        elif active:
            db.stop_active(stop_epoch=ts, activity=activity)
        else:
            db.create_record(
                start_epoch=ts,
                stop_epoch=ts,
                activity=activity,
                device_id=event.device_id,
                volume_ml=_feeding_volume(activity, cfg.get("default_volume_ml")),
            )
    return state_payload()


@app.get("/api/state")
async def api_get_state():
    return state_payload()


@app.get("/api/records")
async def api_list_records(limit: int = 100, date: Optional[str] = None):
    if date is None:
        return db.list_records(limit=limit)
    return _day_payload(_valid_date(date))


def _record_date_epoch(record: dict) -> int:
    """Timestamp used to place a record on a calendar day.

    Milk, Solid food, sleep, Poopoo, and Supplement are logged by end time;
    other session types retain their historical start-time grouping.
    """
    if (
        config.canonical_activity(record.get("activity") or "")
        in {"feeding", "solid_food", "sleep", "poopoo", "supplement"}
        and record.get("stop_epoch") is not None
    ):
        return int(record["stop_epoch"])
    return int(record["start_epoch"])


def _day_payload(date: str) -> dict:
    """All records on `date` (gateway-local), its day note, and a feeding
    summary. The date bucketing matches the web UI's date grouping, and
    `feeds`/`total_ml` use the same volume-bearing-feeding convention as the
    date header, so the numbers line up with what the browser shows."""
    tz = zoneinfo(config.load().get("timezone") or "UTC")
    rows = [
        r for r in db.list_records()
        if datetime.fromtimestamp(_record_date_epoch(r), tz=tz).strftime("%Y-%m-%d") == date
    ]
    rows.reverse()  # oldest-first reads like a daily log
    return {
        "date": date,
        "records": rows,
        "day_note": db.get_day_notes([date]).get(date, ""),
        "summary": {
            "feeds": sum(
                1 for r in rows if r["activity"] == "feeding" and r["volume_ml"]
            ),
            "total_ml": sum(
                (r["volume_ml"] or 0)
                for r in rows
                if r["activity"] == "feeding"
            ),
            "total_g": sum(
                (r["volume_g"] or 0)
                for r in rows
                if r["activity"] == "solid_food"
            ),
            "poopoo": sum(
                1
                for r in rows
                if config.canonical_activity(r["activity"]) == "poopoo"
            ),
        },
    }


class RecordIn(BaseModel):
    start: Optional[int | str] = None
    stop: Optional[int | str] = None
    volume_ml: Optional[int] = None
    volume_g: Optional[int] = None
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
    cfg = config.load()
    tz = cfg.get("timezone") or "UTC"
    activity = config.canonical_activity(body.activity) or "feeding"
    start = _to_epoch(body.start, tz)
    if start is None:
        raise HTTPException(400, "start is required")
    if activity in {"feeding", "solid_food"}:
        # A supplied stop is explicit End; otherwise the older single `start`
        # field is interpreted as End. Start is derived from configured duration.
        end = _to_epoch(body.stop, tz) or start
        start, stop = _feeding_bounds(end, cfg)
    elif activity in {"poopoo", "supplement"}:
        end = _to_epoch(body.stop, tz) or start
        start = stop = end
    else:
        stop = _normalize_stop_epoch(start, _to_epoch(body.stop, tz), activity)
    rid = db.create_record(
        start_epoch=start,
        stop_epoch=stop,
        volume_ml=_feeding_volume(activity, body.volume_ml),
        volume_g=_solid_food_weight(activity, body.volume_g),
        activity=activity,
        notes=body.notes or None,
        device_id=body.device_id or "agent",
    )
    return _require_record(rid)


@app.patch("/api/records/{rid}")
async def api_update_record(rid: int, body: RecordIn):
    existing = _require_record(rid)
    cfg = config.load()
    tz = cfg.get("timezone") or "UTC"
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
        fields["activity"] = config.canonical_activity(provided["activity"]) or "feeding"

    effective_activity = fields.get("activity") or config.canonical_activity(
        existing["activity"]
    )
    if effective_activity == "feeding":
        fields["volume_g"] = None
        if "volume_ml" in provided:
            fields["volume_ml"] = _feeding_volume(
                effective_activity, provided["volume_ml"]
            )
        elif "activity" in provided:
            fields["volume_ml"] = None
    elif effective_activity == "solid_food":
        fields["volume_ml"] = None
        if "volume_g" in provided:
            fields["volume_g"] = _solid_food_weight(
                effective_activity, provided["volume_g"]
            )
        elif "activity" in provided:
            fields["volume_g"] = None
    else:
        fields["volume_ml"] = None
        fields["volume_g"] = None

    time_or_activity_changed = (
        "activity" in provided or "start_epoch" in fields or "stop_epoch" in fields
    )
    if effective_activity in {
        "feeding",
        "solid_food",
        "poopoo",
        "supplement",
    } and time_or_activity_changed:
        end_epoch = (
            fields.get("stop_epoch")
            or fields.get("start_epoch")
            or existing.get("stop_epoch")
            or existing["start_epoch"]
        )
        if effective_activity in {"feeding", "solid_food"}:
            fields["start_epoch"], fields["stop_epoch"] = _feeding_bounds(end_epoch, cfg)
        else:
            fields["start_epoch"] = fields["stop_epoch"] = end_epoch
    elif "start_epoch" in fields or "stop_epoch" in fields:
        start_epoch = fields.get("start_epoch", existing["start_epoch"])
        stop_epoch = fields.get("stop_epoch", existing["stop_epoch"])
        fields["stop_epoch"] = _normalize_stop_epoch(
            start_epoch,
            stop_epoch,
            effective_activity,
        )

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
        d = datetime.fromtimestamp(_record_date_epoch(r), tz=tz).strftime("%Y-%m-%d")
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
            "ml_count": sum(
                1
                for r in by_date[d]
                if r["activity"] == "feeding" and r["volume_ml"]
            ),
            "total_ml": sum(
                (r["volume_ml"] or 0)
                for r in by_date[d]
                if r["activity"] == "feeding"
            ),
            "total_g": sum(
                (r["volume_g"] or 0)
                for r in by_date[d]
                if r["activity"] == "solid_food"
            ),
            "poopoo_count": sum(
                1
                for r in by_date[d]
                if config.canonical_activity(r["activity"]) == "poopoo"
            ),
            "note": day_notes.get(d, ""),
        }
        for d in page_dates
    ]

    activities = config.activity_list(cfg)
    timed = config.timed_activities(cfg)
    # Surface normal Sleep timers and legacy open Milk sessions so they can
    # be closed. Solid food, Poopoo, Supplement, and Etc open their dialogs.
    active_map = {
        a: s for a in activities
        if config.canonical_activity(a)
        not in {"solid_food", "poopoo", "supplement", "etc"}
        and (a in timed or a in {"feeding", "sleep"})
        and (s := db.get_active(a))
    }
    last_fed = next(
        (r for r in all_records
         if r.get("stop_epoch") and r["activity"] == "feeding"),
        None,
    )
    feeding_alert = _feeding_alert_payload(
        cfg,
        active_map.get("feeding"),
        last_fed,
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
            "pol": (lambda name: i18n.poopoo_option_label(name, lang)),
            "groups": groups,
            "activities": activities,
            "languages": i18n.language_options(),
            "timed": sorted(timed),
            "active_map": active_map,
            "last_fed": last_fed,
            "feeding_alert": feeding_alert,
            "config": cfg,
            "poopoo_options": config.poopoo_options(cfg),
            "supplement_options": config.supplement_options(cfg),
            "tz": tz_name,
            "now_date": now.strftime("%Y-%m-%d"),
            "now_time": now.strftime("%H:%M"),
            "page": page,
            "total_pages": total_pages,
            "total_records": len(all_records),
            "total_dates": total_dates,
            "dates_per_page": dates_per_page,
            "max_record_duration_minutes": MAX_RECORD_DURATION_SECONDS // 60,
            "config_keys_simple": [
                "auto_stop_minutes",
                "feeding_alert_minutes",
                "default_volume_ml",
                "timezone",
                "ui_show_count",
                "trusted_networks",
                "trusted_proxies",
            ],
        },
    )


def _feeding_volume(activity: str, raw_ml) -> Optional[int]:
    """Milk volume is only meaningful for the historical ``feeding`` type.

    Accepts a raw form string or an int/None so browser and JSON writes share
    the same normalization rule.
    """
    if activity != "feeding" or raw_ml is None:
        return None
    s = str(raw_ml).strip()
    return int(s) if s else None


def _solid_food_weight(activity: str, raw_g) -> Optional[int]:
    """Gram amount is only meaningful for Solid food records."""
    if activity != "solid_food" or raw_g is None:
        return None
    value = str(raw_g).strip()
    return int(value) if value else None


def _intake_amounts(activity: str, raw_amount) -> tuple[Optional[int], Optional[int]]:
    """Map the UI's shared amount input to its unit-specific DB column."""
    return (
        _feeding_volume(activity, raw_amount),
        _solid_food_weight(activity, raw_amount),
    )


@app.post("/ui/activity")
async def ui_activity_toggle(activity: str = Form("feeding")):
    activity = config.canonical_activity(activity) or "feeding"
    ts = int(time.time())
    cfg = config.load()
    if activity in {"feeding", "solid_food"}:
        # The normal browser path opens an amount-entry dialog and posts to
        # /records. Keep direct/form-only callers fixed-duration too.
        start_epoch, stop_epoch = _feeding_bounds(ts, cfg)
        active = db.get_active(activity) if activity == "feeding" else None
        if active and activity == "feeding":
            db.update_record(
                active["id"],
                start_epoch=start_epoch,
                stop_epoch=stop_epoch,
            )
        else:
            db.create_record(
                start_epoch=start_epoch,
                stop_epoch=stop_epoch,
                activity=activity,
                device_id="web",
                volume_ml=_feeding_volume(activity, cfg.get("default_volume_ml")),
            )
    elif activity in {"poopoo", "supplement", "etc"}:
        # The browser normally uses the popup. A direct call still creates a
        # new independent point record and ignores any older active record.
        db.create_record(
            start_epoch=ts,
            stop_epoch=ts,
            activity=activity,
            device_id="web",
        )
    elif activity not in config.timed_activities(cfg):
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
        )
    return RedirectResponse("/", status_code=303)


@app.post("/records")
async def ui_create(
    date: str = Form(...),
    end_time: str = Form(""),
    duration: str = Form(""),
    start_time: str = Form(""),
    stop_time: str = Form(""),
    amount: str = Form(""),
    volume_ml: str = Form(""),
    activity: str = Form("feeding"),
    notes: str = Form(""),
    poopoo_amount: str = Form(""),
    poopoo_color: str = Form(""),
    poopoo_texture: str = Form(""),
    supplement_type: str = Form(""),
):
    cfg = config.load()
    tz = cfg.get("timezone") or "UTC"
    activity = config.canonical_activity(activity) or "feeding"

    # Milk and Solid food derive Start from a fixed duration. Sleep accepts an
    # explicit HH:MM duration. Poopoo and Supplement are independent point
    # records. Etc accepts explicit Start and End fields.
    if end_time.strip():
        end_epoch = combine_date_time(date, end_time, tz)
        if end_epoch is None:
            raise HTTPException(400, "date and end_time required")
        if activity in {"feeding", "solid_food"}:
            start_epoch, stop_epoch = _feeding_bounds(end_epoch, cfg)
        elif activity in {"poopoo", "supplement"}:
            start_epoch = stop_epoch = end_epoch
        elif activity == "sleep" and not start_time.strip():
            stop_epoch = end_epoch
            start_epoch = end_epoch - _duration_hhmm_seconds(duration)
        elif start_time.strip():
            start_epoch = combine_date_time(date, start_time, tz)
            if start_epoch is None:
                raise HTTPException(400, "date and start_time required")
            stop_epoch = _normalize_stop_epoch(start_epoch, end_epoch, activity)
        else:
            start_epoch = end_epoch
            stop_epoch = end_epoch
    else:
        start_epoch = combine_date_time(date, start_time, tz)
        if start_epoch is None:
            raise HTTPException(400, "date and end_time required")
        if activity not in config.timed_activities(cfg):
            stop_epoch = start_epoch  # instant event: a single closed timestamp
        else:
            stop_epoch = combine_date_time(date, stop_time, tz) if stop_time.strip() else None
            stop_epoch = _normalize_stop_epoch(start_epoch, stop_epoch, activity)
    if activity == "poopoo":
        notes = _poopoo_notes(
            cfg,
            poopoo_amount,
            poopoo_color,
            poopoo_texture,
            notes,
        )
    elif activity == "supplement":
        notes = _supplement_notes(cfg, supplement_type, notes)
    raw_amount = amount if amount.strip() else volume_ml
    stored_ml, stored_g = _intake_amounts(activity, raw_amount)
    db.create_record(
        start_epoch=start_epoch,
        stop_epoch=stop_epoch,
        volume_ml=stored_ml,
        volume_g=stored_g,
        activity=activity,
        notes=notes.strip() or None,
        device_id="web",
    )
    return RedirectResponse("/", status_code=303)


@app.post("/records/save")
async def ui_bulk_save(request: Request):
    cfg = config.load()
    tz = cfg.get("timezone") or "UTC"
    form = await request.form()
    timed = config.timed_activities(cfg)
    rids = [int(v) for v in form.getlist("record_id") if str(v).isdigit()]
    existing_by_id = {r["id"]: r for r in db.list_records(ids=rids)} if rids else {}
    for rid in rids:
        date = (form.get(f"date_{rid}") or "").strip()
        start_time = (form.get(f"start_time_{rid}") or "").strip()
        stop_time = (form.get(f"stop_time_{rid}") or "").strip()
        if not date or (not start_time and not stop_time):
            continue
        activity = config.canonical_activity(
            form.get(f"activity_{rid}") or "feeding"
        ) or "feeding"
        existing = existing_by_id.get(rid)
        if activity in {"feeding", "solid_food"}:
            end_epoch = combine_date_time(date, stop_time or start_time, tz)
            if end_epoch is None:
                continue
            start_epoch, stop_epoch = _feeding_bounds(end_epoch, cfg)
        elif activity in {"poopoo", "supplement"}:
            end_epoch = combine_date_time(date, stop_time or start_time, tz)
            if end_epoch is None:
                continue
            start_epoch = stop_epoch = end_epoch
        elif not start_time:
            # Completed point-in-time rows expose only their end time. Keep
            # the schema's two columns equal when that end is edited.
            end_epoch = combine_date_time(date, stop_time, tz)
            start_epoch = end_epoch
            stop_epoch = end_epoch
        else:
            start_epoch = combine_date_time(date, start_time, tz)
            if activity not in timed and activity not in {"sleep", "etc"}:
                stop_epoch = start_epoch
            else:
                stop_epoch = combine_date_time(date, stop_time, tz) if stop_time else None
                stop_epoch = _normalize_stop_epoch(start_epoch, stop_epoch, activity)
        if start_epoch is None or (existing is None):
            continue
        raw_amount = form.get(f"amount_{rid}")
        if raw_amount is None:
            legacy_key = "volume_g" if activity == "solid_food" else "volume_ml"
            raw_amount = form.get(f"{legacy_key}_{rid}") or ""
        volume_ml, volume_g = _intake_amounts(activity, raw_amount)
        db.update_record(
            rid,
            start_epoch=start_epoch,
            stop_epoch=stop_epoch,
            volume_ml=volume_ml,
            volume_g=volume_g,
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
    poopoo_rows: dict[str, list[str]] = {
        key: [] for key in config.POOPOO_OPTION_KEYS.values()
    }
    poopoo_options_present = False
    supplement_rows: list[str] = []
    supplement_options_present = False
    for key, value in form.multi_items():
        if key.startswith("activity_name_"):
            rows.append((key[len("activity_name_"):], str(value).strip()))
        elif key.startswith("activity_timed_"):
            timed_rows.add(key[len("activity_timed_"):])
        elif key == "poopoo_options_present":
            poopoo_options_present = True
        elif key == "supplement_options_present":
            supplement_options_present = True
        elif key.startswith("supplement_options_item_"):
            option = str(value).strip()
            if "," in option:
                raise HTTPException(400, "supplement options cannot contain commas")
            if option:
                supplement_rows.append(option)
        else:
            option_key = next(
                (
                    config_key
                    for config_key in poopoo_rows
                    if key.startswith(config_key + "_item_")
                ),
                None,
            )
            if option_key:
                option = str(value).strip()
                if "," in option:
                    raise HTTPException(400, "poopoo options cannot contain commas")
                if option:
                    poopoo_rows[option_key].append(option)
            else:
                items[key] = str(value)
    if rows:
        # Rebuild the two activity lists from the per-row name + timed toggle.
        # Disabled end-time toggles need not round-trip; config parsing keeps
        # Built-in end-time activities stay out of the timed activity set.
        items["activity_types"] = ",".join(name for _, name in rows if name)
        items["timed_activities"] = ",".join(
            name
            for ri, name in rows
            if config.canonical_activity(name)
            not in {"feeding", "solid_food", "poopoo", "supplement"}
            and name
            and (ri in timed_rows or config.canonical_activity(name) == "etc")
        )
    if poopoo_options_present:
        for key, values in poopoo_rows.items():
            items[key] = ",".join(dict.fromkeys(values))
    if supplement_options_present:
        items["supplement_options"] = ",".join(dict.fromkeys(supplement_rows))
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
