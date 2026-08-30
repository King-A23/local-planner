"""Idempotent last_settled_date watermark. Caller owns the transaction."""

from __future__ import annotations

from datetime import date, timedelta

from local_planner.clock import Clock
from local_planner.domain.models import CalendarDate
from local_planner.domain.seal import settle_one_day
from local_planner.domain.store import UnitOfWork


def inclusive_range(start: CalendarDate, end: CalendarDate) -> list[CalendarDate]:
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    out: list[CalendarDate] = []
    d = s
    while d <= e:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def day_before(d: CalendarDate) -> CalendarDate:
    return (date.fromisoformat(d) - timedelta(days=1)).isoformat()


def earliest_relevant_date(uow: UnitOfWork) -> CalendarDate | None:
    """min(days.date, entries, errands, tasks.current_scheduled_date)."""
    return uow.earliest_relevant_date()


def ensure_settled(clock: Clock, uow: UnitOfWork) -> None:
    """Pure domain: no lock, no BEGIN. Caller must already be in uow.transaction()."""
    today = clock.today()  # 事务内再读一次，见 §4.1.1
    last = uow.meta.get("last_settled_date")
    if last is None:
        if uow.is_proven_empty():
            # 无 days / day_task_entries / errands 行：真正的空库
            uow.meta.set("last_settled_date", today)
            return
        # 备份恢复、meta 丢失、测试先插日后写 meta：不得把水位直接跳到 today
        earliest = earliest_relevant_date(uow)
        if earliest is None or earliest >= today:
            uow.meta.set("last_settled_date", today)
            return
        last = earliest
    if last >= today:
        return
    # [last, today)：last=8-30 且 today=8-31 → 封印 8-30
    for d in inclusive_range(last, day_before(today)):
        settle_one_day(d, clock.now_utc(), uow)
    uow.meta.set("last_settled_date", today)
