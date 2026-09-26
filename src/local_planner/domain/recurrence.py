"""Recurring templates and idempotent occurrence materialization."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import date
from typing import Iterable

from local_planner.clock import Clock, format_utc
from local_planner.domain.errors import Conflict, NotFound, ValidationError
from local_planner.domain.models import (
    CalendarDate,
    DayRecord,
    DayTaskEntry,
    Errand,
    RecurrenceFrequency,
    RecurrenceKind,
    RecurrenceOccurrence,
    RecurrenceSeries,
    Task,
    add_calendar_days,
    check_year_cap,
    normalize_title,
    parse_calendar_date,
)
from local_planner.domain.store import UnitOfWork
from local_planner.domain.time import validate_clock_pair

WEEKDAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_WEEKDAY_BITS = {name: 1 << index for index, name in enumerate(WEEKDAY_NAMES)}
ALL_WEEKDAYS_MASK = 127
UNSET = object()


def weekdays_to_mask(frequency: str, weekdays: Iterable[str] | None) -> int:
    if frequency not in ("daily", "weekly"):
        raise ValidationError("重复频率无效")
    if frequency == "daily":
        return ALL_WEEKDAYS_MASK
    mask = 0
    for raw in weekdays or ():
        name = str(raw).strip().lower()
        bit = _WEEKDAY_BITS.get(name)
        if bit is None:
            raise ValidationError("星期值无效")
        mask |= bit
    if mask == 0:
        raise ValidationError("每周重复至少选择一天")
    return mask


def mask_to_weekdays(mask: int) -> list[str]:
    return [name for index, name in enumerate(WEEKDAY_NAMES) if mask & (1 << index)]


def recurrence_matches(series: RecurrenceSeries, d: CalendarDate) -> bool:
    if series.state != "active" or d < series.start_date or d < series.schedule_from:
        return False
    weekday = parse_calendar_date(d).weekday()
    return bool(series.weekdays_mask & (1 << weekday))


def create_recurrence(
    clock: Clock,
    uow: UnitOfWork,
    *,
    kind: str,
    title: str,
    frequency: str,
    weekdays: Iterable[str] | None,
    start_date: str,
    default_start_clock: str | None = None,
    default_end_clock: str | None = None,
) -> RecurrenceSeries:
    if kind not in ("plan", "errand"):
        raise ValidationError("定期类型无效")
    title = normalize_title(title)
    start = parse_calendar_date(start_date).isoformat()
    today = clock.today()
    check_year_cap(start, today)
    if start < today:
        raise ValidationError("定期事项开始日期不能早于今天")
    mask = weekdays_to_mask(frequency, weekdays)
    start_clock, end_clock = validate_clock_pair(
        default_start_clock, default_end_clock
    )
    now = format_utc(clock.now_utc())
    series = RecurrenceSeries(
        id=str(uuid.uuid4()),
        kind=kind,  # type: ignore[arg-type]
        title=title,
        frequency=frequency,  # type: ignore[arg-type]
        weekdays_mask=mask,
        start_date=start,
        schedule_from=max(start, today),
        default_start_clock=start_clock,
        default_end_clock=end_clock,
        state="active",
        created_at=now,
        updated_at=now,
        paused_at=None,
        stopped_at=None,
        deleted_at=None,
    )
    uow.save_recurrence(series)
    materialize_occurrences_for_date(clock, uow, today)
    return series


def update_recurrence(
    clock: Clock,
    uow: UnitOfWork,
    series_id: str,
    *,
    title: str | object = UNSET,
    frequency: str | object = UNSET,
    weekdays: Iterable[str] | None | object = UNSET,
    start_date: str | object = UNSET,
    default_start_clock: str | None | object = UNSET,
    default_end_clock: str | None | object = UNSET,
) -> RecurrenceSeries:
    current = require_recurrence(uow, series_id)
    if current.state == "stopped":
        raise Conflict("已停止的定期事项不能修改")
    next_title = current.title if title is UNSET else normalize_title(title)  # type: ignore[arg-type]
    next_frequency = (
        current.frequency if frequency is UNSET else str(frequency).strip().lower()
    )
    if weekdays is UNSET and frequency is UNSET:
        next_mask = current.weekdays_mask
    else:
        values = (
            mask_to_weekdays(current.weekdays_mask)
            if weekdays is UNSET
            else weekdays
        )
        next_mask = weekdays_to_mask(next_frequency, values)  # type: ignore[arg-type]
    next_start = current.start_date
    if start_date is not UNSET:
        next_start = parse_calendar_date(str(start_date)).isoformat()
        check_year_cap(next_start, clock.today())
        if next_start < clock.today():
            raise ValidationError("定期事项开始日期不能早于今天")
    start_clock = (
        current.default_start_clock
        if default_start_clock is UNSET
        else default_start_clock
    )
    end_clock = (
        current.default_end_clock if default_end_clock is UNSET else default_end_clock
    )
    start_clock, end_clock = validate_clock_pair(  # type: ignore[arg-type]
        start_clock, end_clock
    )
    today = clock.today()
    updated = replace(
        current,
        title=next_title,
        frequency=next_frequency,  # type: ignore[arg-type]
        weekdays_mask=next_mask,
        start_date=next_start,
        schedule_from=max(add_calendar_days(today, 1), next_start),
        default_start_clock=start_clock,
        default_end_clock=end_clock,
        updated_at=format_utc(clock.now_utc()),
    )
    uow.save_recurrence(updated)
    return updated


def pause_recurrence(
    clock: Clock, uow: UnitOfWork, series_id: str
) -> RecurrenceSeries:
    current = require_recurrence(uow, series_id)
    if current.state == "stopped":
        raise Conflict("已停止的定期事项不能暂停")
    if current.state == "paused":
        return current
    now = format_utc(clock.now_utc())
    updated = replace(current, state="paused", paused_at=now, updated_at=now)
    uow.save_recurrence(updated)
    return updated


def resume_recurrence(
    clock: Clock, uow: UnitOfWork, series_id: str
) -> RecurrenceSeries:
    current = require_recurrence(uow, series_id)
    if current.state == "stopped":
        raise Conflict("已停止的定期事项不能恢复")
    if current.state == "active":
        return current
    now = format_utc(clock.now_utc())
    updated = replace(
        current,
        state="active",
        schedule_from=max(clock.today(), current.start_date),
        paused_at=None,
        updated_at=now,
    )
    uow.save_recurrence(updated)
    materialize_occurrences_for_date(clock, uow, clock.today())
    return updated


def stop_recurrence(
    clock: Clock, uow: UnitOfWork, series_id: str
) -> RecurrenceSeries:
    current = require_recurrence(uow, series_id)
    if current.state == "stopped":
        return current
    now = format_utc(clock.now_utc())
    updated = replace(current, state="stopped", stopped_at=now, updated_at=now)
    uow.save_recurrence(updated)
    return updated


def delete_recurrence(
    clock: Clock, uow: UnitOfWork, series_id: str
) -> RecurrenceSeries:
    """Hide a stopped series while retaining it as occurrence provenance."""
    current = require_recurrence(uow, series_id)
    if current.state != "stopped":
        raise Conflict("只有已停止的定期事项可以删除")
    now = format_utc(clock.now_utc())
    deleted = replace(current, deleted_at=now, updated_at=now)
    uow.save_recurrence(deleted)
    return deleted


def require_recurrence(uow: UnitOfWork, series_id: str) -> RecurrenceSeries:
    series = uow.get_recurrence(series_id)
    if series is None or series.deleted_at is not None:
        raise NotFound("找不到该定期事项")
    return series


def materialize_occurrences_for_date(
    clock: Clock, uow: UnitOfWork, d: CalendarDate
) -> None:
    occurrence_date = parse_calendar_date(d).isoformat()
    for series in uow.list_recurrences():
        if not recurrence_matches(series, occurrence_date):
            continue
        if uow.get_occurrence(series.id, occurrence_date) is not None:
            continue
        _materialize_one(clock, uow, series, occurrence_date)


def _materialize_one(
    clock: Clock,
    uow: UnitOfWork,
    series: RecurrenceSeries,
    occurrence_date: CalendarDate,
) -> None:
    now = format_utc(clock.now_utc())
    record = uow.get_day(occurrence_date)
    if record is not None and record.status == "sealed":
        uow.save_occurrence(
            RecurrenceOccurrence(
                series_id=series.id,
                occurrence_date=occurrence_date,
                kind=series.kind,
                entity_id=None,
                disposition="skipped_sealed",
                generated_at=now,
            )
        )
        return
    if record is None:
        uow.save_day(DayRecord(date=occurrence_date, status="open", sealed_at=None))
    entity_id = str(uuid.uuid4())
    if series.kind == "plan":
        task = Task(
            id=entity_id,
            title=series.title,
            created_at=now,
            current_scheduled_date=occurrence_date,
            completed_at=None,
            completed_on_date=None,
            series_id=series.id,
            occurrence_date=occurrence_date,
        )
        uow.save_task(task)
        entries = uow.list_entries(occurrence_date)
        uow.save_entry(
            DayTaskEntry(
                day_date=occurrence_date,
                task_id=entity_id,
                title_snapshot=series.title,
                sort_order=_next_sort(entries),
                completed_on_day=False,
                start_clock=series.default_start_clock,
                end_clock=series.default_end_clock,
                series_id=series.id,
                occurrence_date=occurrence_date,
            )
        )
    else:
        errands = uow.list_errands(occurrence_date)
        uow.save_errand(
            Errand(
                id=entity_id,
                day_date=occurrence_date,
                title=series.title,
                sort_order=_next_sort(errands),
                status="open",
                completed_at=None,
                start_clock=series.default_start_clock,
                end_clock=series.default_end_clock,
                series_id=series.id,
                occurrence_date=occurrence_date,
            )
        )
    uow.save_occurrence(
        RecurrenceOccurrence(
            series_id=series.id,
            occurrence_date=occurrence_date,
            kind=series.kind,
            entity_id=entity_id,
            disposition="materialized",
            generated_at=now,
        )
    )


def _next_sort(items: list[DayTaskEntry] | list[Errand]) -> int:
    return 0 if not items else max(item.sort_order for item in items) + 1
