import ipaddress
import json
import os
import threading
from pathlib import Path
from typing import Callable, Optional

CONFIG_PATH = os.environ.get("GATEWAY_CONFIG_PATH", "/babytime/config.json")

DEFAULTS: dict = {
    "activity_types": "feeding,sleep,poopoo",
    "timed_activities": "feeding,sleep",
    "auto_stop_minutes": "15",
    "feeding_alert_minutes": "120",
    "default_volume_ml": "",
    "default_language": "en",
    "timezone": "UTC",
    "ui_show_count": "10",
    "trusted_networks": "10.0.0.0/8",
    "trusted_proxies": "",
}

_lock = threading.Lock()
_cache: Optional[dict] = None


def _coerce(v) -> str:
    if isinstance(v, bool):
        return "1" if v else "0"
    return "" if v is None else str(v)


def _read_file() -> dict:
    p = Path(CONFIG_PATH)
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_file(data: dict) -> None:
    p = Path(CONFIG_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, p)


def _merge(file_data: dict) -> dict:
    merged = {**DEFAULTS}
    for k, v in file_data.items():
        merged[k] = _coerce(v)
    return merged


def load() -> dict:
    global _cache
    with _lock:
        if _cache is None:
            file_data = _read_file()
            if not Path(CONFIG_PATH).exists():
                _write_file({**DEFAULTS})
            _cache = _merge(file_data)
        return dict(_cache)


def update(items: dict) -> dict:
    global _cache
    with _lock:
        current = _read_file()
        for k, v in items.items():
            current[k] = _coerce(v)
        _write_file(current)
        _cache = _merge(current)
        return dict(_cache)


def activity_list(cfg: dict) -> list:
    """Configured activity types, in order, deduped, with 'feeding' first.

    'feeding' is the one type the rest of the app special-cases (volume_ml,
    the firmware default), so it is always present regardless of config.
    """
    raw = (cfg.get("activity_types") or "").replace("\n", ",")
    seen: set = set()
    out: list = ["feeding"]
    seen.add("feeding")
    for part in raw.split(","):
        name = part.strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _parse_cidrs(raw: str) -> list:
    """Comma/newline-separated CIDR string → list of `ip_network`. Unparseable
    entries are dropped rather than raising, so one typo in the config can't
    lock the whole UI out."""
    nets: list = []
    for part in (raw or "").replace("\n", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            nets.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            pass
    return nets


def trusted_networks(cfg: dict) -> list:
    """Parsed CIDR blocks whose clients skip authentication.

    Browsers and API clients from these networks are treated as logged in
    (the gateway is meant to be open on the home LAN); everyone else must
    present the gateway token."""
    return _parse_cidrs(cfg.get("trusted_networks") or "")


def trusted_proxies(cfg: dict) -> list:
    """Parsed CIDR blocks of reverse proxies whose `X-Forwarded-For` we
    believe. Empty by default: the forwarded header is ignored unless the
    direct peer is a configured proxy, so a client can't spoof a LAN IP to
    bypass auth."""
    return _parse_cidrs(cfg.get("trusted_proxies") or "")


def int_value(cfg: dict, key: str, default: int = 0, minimum: Optional[int] = None) -> int:
    """Parse an integer config value, falling back on bad input.

    Config is user-editable text, so callers that need arithmetic should avoid
    open-coding `int(...)` and accidentally breaking a route on one bad field.
    """
    try:
        value = int(str(cfg.get(key) or "").strip())
    except (TypeError, ValueError):
        value = default
    if minimum is not None and value < minimum:
        return minimum
    return value


def feeding_alert_minutes(cfg: dict) -> int:
    """Minutes after the last completed feeding before the due alert fires.

    `0` disables the alert. The default is two hours.
    """
    return int_value(cfg, "feeding_alert_minutes", default=120, minimum=0)


def timed_activities(cfg: dict) -> set:
    """Activities recorded as start->stop sessions (running timer); the rest
    are instant timestamps (start only, stop shown as '-').

    'feeding' is always timed — the firmware's session model and the volume
    logic both assume a feeding session that opens and closes."""
    raw = (cfg.get("timed_activities") or "").replace("\n", ",")
    out = {"feeding"}
    for part in raw.split(","):
        name = part.strip()
        if name:
            out.add(name)
    return out


def migrate_from(legacy_loader: Callable[[], dict]) -> None:
    if Path(CONFIG_PATH).exists():
        return
    rows = legacy_loader() or {}
    seed = {**DEFAULTS, **{k: _coerce(v) for k, v in rows.items()}}
    _write_file(seed)
