from datetime import datetime, timedelta, timezone
from typing import Optional

# Activities long enough to be worth keeping on both sides of midnight. Every
# other type is short, so its after-midnight tail is dropped instead.
SPLIT_ACTIVITIES = {"sleep"}


def zoneinfo(tz_name: str):
    """Resolve an IANA timezone name, falling back to UTC if zoneinfo is
    unavailable (e.g. base image without tzdata)."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_name)
    except Exception:
        return timezone.utc


def local_midnight_after(epoch: int, tz_name: str = "UTC") -> int:
    """Epoch of the first local `00:00` strictly after `epoch`."""
    dt = datetime.fromtimestamp(int(epoch), tz=zoneinfo(tz_name))
    nxt = (dt + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(nxt.timestamp())


def midnight_segments(
    start_epoch: int,
    stop_epoch: Optional[int],
    activity: str,
    tz_name: str = "UTC",
) -> list:
    """Cut a span so that no stored record crosses local midnight.

    Sleep becomes one segment per calendar day — 19:00→01:00 gives
    `19:00–23:59:59` and `00:00:00–01:00`. Every other activity is clamped to
    the end of the day it started on, so a 23:50→00:05 feed is filed as
    `23:50–23:59:59` on the earlier day. A still-open span (`stop_epoch` is
    `None`) is returned unchanged; it gets cut when it is closed.
    """
    if stop_epoch is None:
        return [(int(start_epoch), None)]
    start, stop = int(start_epoch), int(stop_epoch)
    boundary = local_midnight_after(start, tz_name)
    if stop < boundary:
        return [(start, stop)]
    if activity not in SPLIT_ACTIVITIES:
        return [(start, boundary - 1)]
    segments = []
    while stop >= boundary:
        segments.append((start, boundary - 1))
        start = boundary
        boundary = local_midnight_after(start, tz_name)
    if stop > start:
        segments.append((start, stop))
    return segments
