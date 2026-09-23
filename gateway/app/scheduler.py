import asyncio
import time

from . import config, db
from .util import midnight_segments


def _enforce_auto_stop(cfg: dict) -> None:
    try:
        minutes = int(cfg.get("auto_stop_minutes") or "15")
    except ValueError:
        minutes = 15
    if minutes <= 0:
        return
    # Sleep runs until manually stopped and must not hide another due timer.
    capped_activities = (config.timed_activities(cfg) | {"feeding"}) - {"sleep"}
    active = max(
        (record for activity in capped_activities if (record := db.get_active(activity))),
        key=lambda record: record["start_epoch"],
        default=None,
    )
    if not active:
        return
    cap = int(active["start_epoch"]) + minutes * 60
    if int(time.time()) >= cap:
        # A long cap can push the close past midnight; store it day by day.
        segments = midnight_segments(
            int(active["start_epoch"]),
            cap,
            active["activity"],
            cfg.get("timezone") or "UTC",
        )
        if db.stop_active(stop_epoch=segments[0][1], activity=active["activity"]):
            db.clone_segments(active["id"], segments[1:])
            print(f"[scheduler] auto-stopped session {active['id']} at {minutes}min cap")


async def scheduler_loop() -> None:
    """Wake every 60 s and cap the newest eligible non-sleep session that has
    outrun `auto_stop_minutes`. Cancellable via CancelledError."""
    try:
        while True:
            await asyncio.sleep(60)
            try:
                _enforce_auto_stop(config.load())
            except Exception as e:
                print(f"[scheduler] error: {e}")
    except asyncio.CancelledError:
        pass
