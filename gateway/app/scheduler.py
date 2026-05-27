import asyncio
import time

from . import config, db


def _enforce_auto_stop(cfg: dict) -> None:
    try:
        minutes = int(cfg.get("auto_stop_minutes") or "15")
    except ValueError:
        minutes = 15
    if minutes <= 0:
        return
    active = db.get_active()
    if not active:
        return
    if active["activity"] not in config.timed_activities(cfg):
        return  # instant events are never open; nothing to cap
    cap = int(active["start_epoch"]) + minutes * 60
    if int(time.time()) >= cap:
        if db.stop_active(stop_epoch=cap):
            print(f"[scheduler] auto-stopped session {active['id']} at {minutes}min cap")


async def scheduler_loop() -> None:
    """Periodic auto-stop loop: wakes every 60 s and caps any active session
    that has outrun `auto_stop_minutes`. Cancellable via CancelledError."""
    try:
        while True:
            await asyncio.sleep(60)
            try:
                _enforce_auto_stop(config.load())
            except Exception as e:
                print(f"[scheduler] error: {e}")
    except asyncio.CancelledError:
        pass
