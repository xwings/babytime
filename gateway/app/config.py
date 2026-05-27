import json
import os
import threading
from pathlib import Path
from typing import Callable, Optional

CONFIG_PATH = os.environ.get("GATEWAY_CONFIG_PATH", "/babytime/config.json")

DEFAULTS: dict = {
    "activity_types": "feeding,sleep,poopoo",
    "auto_stop_minutes": "15",
    "default_volume_ml": "",
    "timezone": "UTC",
    "ui_show_count": "10",
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


def migrate_from(legacy_loader: Callable[[], dict]) -> None:
    if Path(CONFIG_PATH).exists():
        return
    rows = legacy_loader() or {}
    seed = {**DEFAULTS, **{k: _coerce(v) for k, v in rows.items()}}
    _write_file(seed)
