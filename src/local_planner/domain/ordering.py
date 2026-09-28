"""One displayed order for JSON views and transactional relative moves."""
from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from local_planner.domain.models import DayTaskEntry, Errand

T = TypeVar("T", DayTaskEntry, Errand)


def ordered_items(items: Sequence[T], *, manual: bool) -> list[T]:
    if manual:
        return sorted(items, key=lambda item: item.sort_order)
    # Timed items first; start (or end if no start), then stored order for ties.
    return sorted(items, key=lambda item: (
        0 if item.start_clock is not None or item.end_clock is not None else 1,
        item.start_clock or item.end_clock or "99:99",
        item.sort_order,
    ))
