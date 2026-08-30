"""seal_day / settle_one_day. Watermark ensure_settled is a later PR."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import datetime

from local_planner.clock import Clock, format_utc
from local_planner.domain.models import CalendarDate, DayRecord, parse_calendar_date
from local_planner.domain.store import UnitOfWork

logger = logging.getLogger(__name__)


def settle_one_day(d: CalendarDate, now: datetime | str, uow: UnitOfWork) -> None:
    """Seal one day: unfinished todos return to inventory, open errands expire.

    Idempotent. Missing day rows are left as virtual empty days (no insert).
    Does not read or write last_settled_date.
    """
    parse_calendar_date(d)
    rec = uow.get_day(d)
    if rec is None or rec.status == "sealed":
        return
    instant = now if isinstance(now, str) else format_utc(now)
    for entry in uow.list_entries(d):
        task = uow.get_task(entry.task_id)
        if entry.completed_on_day:
            if task is not None and task.completed_at is None:
                logger.error(
                    "sealed snapshot completed_on_day=1 but task not completed task_id=%s date=%s",
                    entry.task_id,
                    d,
                )
            continue
        if (
            task is not None
            and task.completed_at is None
            and task.current_scheduled_date == d
        ):
            uow.save_task(replace(task, current_scheduled_date=None))
    for errand in uow.list_errands(d):
        if errand.status == "open":
            uow.save_errand(replace(errand, status="expired", completed_at=None))
    uow.save_day(DayRecord(date=d, status="sealed", sealed_at=instant))


def seal_day(clock: Clock, uow: UnitOfWork, d: CalendarDate) -> None:
    """Test/domain primitive with the same effect as settle_one_day."""
    settle_one_day(d, clock.now_utc(), uow)
