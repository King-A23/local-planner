"""Optional clock values: HH:MM on a 5-minute grid, same civil day."""

from __future__ import annotations

import re

from local_planner.domain.errors import ValidationError

_CLOCK = re.compile(r"^(\d{1,2})(?::([0-5]\d))?$")


def parse_clock(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    match = _CLOCK.fullmatch(text)
    if not match:
        raise ValidationError("时刻格式无效")
    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    if hour > 23 or minute % 5 != 0:
        raise ValidationError("时刻须为当天 5 分钟整点")
    return f"{hour:02d}:{minute:02d}"


def validate_clock_pair(
    start: str | None, end: str | None
) -> tuple[str | None, str | None]:
    start_clock = parse_clock(start)
    end_clock = parse_clock(end)
    if start_clock and end_clock and end_clock < start_clock:
        raise ValidationError("结束不得早于开始")
    return start_clock, end_clock
