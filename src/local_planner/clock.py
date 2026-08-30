"""Injectable clocks. Calendar days are always Asia/Shanghai civil dates."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")

CalendarDate = str  # YYYY-MM-DD
UtcInstant = str  # YYYY-MM-DDTHH:MM:SSZ


def format_utc(dt: datetime) -> UtcInstant:
    """Seconds, literal Z, no millis, no +00:00 offset spelling."""
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def shanghai_date(value: datetime | str) -> CalendarDate:
    """Convert a UTC instant or aware datetime to the Shanghai civil date."""
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        dt = value
    if dt.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return dt.astimezone(SHANGHAI).date().isoformat()


def parse_instant(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=SHANGHAI)
    return dt


class Clock(Protocol):
    def now_utc(self) -> datetime: ...

    def today(self) -> CalendarDate: ...


class SystemClock:
    """Production clock. Civil today is ZoneInfo Asia/Shanghai, not the OS zone."""

    def now_utc(self) -> datetime:
        return datetime.now(timezone.utc).replace(microsecond=0)

    def today(self) -> CalendarDate:
        return datetime.now(SHANGHAI).date().isoformat()


class FrozenClock:
    """Test clock pinned to one instant. `set` advances time in-process."""

    def __init__(self, instant: str | datetime) -> None:
        self._now = parse_instant(instant)

    def set(self, instant: str | datetime) -> None:
        self._now = parse_instant(instant)

    def now_utc(self) -> datetime:
        return self._now.astimezone(timezone.utc).replace(microsecond=0)

    def today(self) -> CalendarDate:
        return self._now.astimezone(SHANGHAI).date().isoformat()
