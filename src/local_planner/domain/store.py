"""Unit of work protocol and in-memory implementation. No SQLite here."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Protocol

from local_planner.domain.errors import Conflict
from local_planner.domain.models import (
    CalendarDate,
    DayRecord,
    DayTaskEntry,
    Errand,
    ErrandId,
    RecurrenceOccurrence,
    RecurrenceSeries,
    Task,
    TaskId,
)


class MetaStore(Protocol):
    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str) -> None: ...


class UnitOfWork(Protocol):
    """Persistence port. Domain never BEGIN/COMMIT; the adapter owns that."""

    meta: MetaStore

    def transaction(self) -> Iterator[None]: ...

    def get_task(self, task_id: TaskId) -> Task | None: ...

    def save_task(self, task: Task) -> None: ...

    def delete_task_row(self, task_id: TaskId) -> None: ...

    def get_day(self, d: CalendarDate) -> DayRecord | None: ...

    def save_day(self, day: DayRecord) -> None: ...

    def get_entry(self, day: CalendarDate, task_id: TaskId) -> DayTaskEntry | None: ...

    def list_entries(self, day: CalendarDate) -> list[DayTaskEntry]: ...

    def list_entries_for_task(self, task_id: TaskId) -> list[DayTaskEntry]: ...

    def save_entry(self, entry: DayTaskEntry) -> None: ...

    def delete_entry(self, day: CalendarDate, task_id: TaskId) -> None: ...

    def get_errand(self, errand_id: ErrandId) -> Errand | None: ...

    def list_errands(self, day: CalendarDate) -> list[Errand]: ...

    def save_errand(self, errand: Errand) -> None: ...

    def delete_errand(self, errand_id: ErrandId) -> None: ...

    def list_inventory_tasks(self) -> list[Task]: ...

    def list_scheduled_after(self, today: CalendarDate) -> list[Task]: ...

    def list_errands_after(self, today: CalendarDate) -> list[Errand]: ...

    def get_recurrence(self, series_id: str) -> RecurrenceSeries | None: ...

    def list_recurrences(self) -> list[RecurrenceSeries]: ...

    def save_recurrence(self, series: RecurrenceSeries) -> None: ...

    def get_occurrence(
        self, series_id: str, occurrence_date: CalendarDate
    ) -> RecurrenceOccurrence | None: ...

    def save_occurrence(self, occurrence: RecurrenceOccurrence) -> None: ...

    def get_planned_at(self, day: CalendarDate) -> str | None: ...

    def set_day_planned(self, day: CalendarDate, planned_at: str) -> None: ...

    def is_proven_empty(self) -> bool: ...

    def earliest_relevant_date(self) -> CalendarDate | None: ...


class InMemoryMeta:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._values.get(key)

    def set(self, key: str, value: str) -> None:
        self._values[key] = value


class InMemoryUnitOfWork:
    """Process-local store for domain unit tests. Same port as persistence."""

    def __init__(self) -> None:
        self._tasks: dict[TaskId, Task] = {}
        self._days: dict[CalendarDate, DayRecord] = {}
        self._entries: dict[tuple[CalendarDate, TaskId], DayTaskEntry] = {}
        self._errands: dict[ErrandId, Errand] = {}
        self._recurrences: dict[str, RecurrenceSeries] = {}
        self._occurrences: dict[tuple[str, CalendarDate], RecurrenceOccurrence] = {}
        self._planned: dict[CalendarDate, str] = {}
        self._task_seq = 0
        self._task_order: dict[TaskId, int] = {}
        self.meta = InMemoryMeta()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        yield

    def get_task(self, task_id: TaskId) -> Task | None:
        return self._tasks.get(task_id)

    def save_task(self, task: Task) -> None:
        if task.id not in self._task_order:
            self._task_seq += 1
            self._task_order[task.id] = self._task_seq
        self._tasks[task.id] = task

    def delete_task_row(self, task_id: TaskId) -> None:
        self._tasks.pop(task_id, None)
        self._task_order.pop(task_id, None)

    def get_day(self, d: CalendarDate) -> DayRecord | None:
        return self._days.get(d)

    def save_day(self, day: DayRecord) -> None:
        self._days[day.date] = day

    def get_entry(self, day: CalendarDate, task_id: TaskId) -> DayTaskEntry | None:
        return self._entries.get((day, task_id))

    def list_entries(self, day: CalendarDate) -> list[DayTaskEntry]:
        found = [e for (d, _), e in self._entries.items() if d == day]
        found.sort(key=lambda e: e.sort_order)
        return found

    def list_entries_for_task(self, task_id: TaskId) -> list[DayTaskEntry]:
        found = [e for (_, tid), e in self._entries.items() if tid == task_id]
        found.sort(key=lambda e: (e.day_date, e.sort_order))
        return found

    def save_entry(self, entry: DayTaskEntry) -> None:
        reject_second_open_schedule(self, entry)
        self._entries[(entry.day_date, entry.task_id)] = entry

    def delete_entry(self, day: CalendarDate, task_id: TaskId) -> None:
        self._entries.pop((day, task_id), None)

    def get_errand(self, errand_id: ErrandId) -> Errand | None:
        return self._errands.get(errand_id)

    def list_errands(self, day: CalendarDate) -> list[Errand]:
        found = [e for e in self._errands.values() if e.day_date == day]
        found.sort(key=lambda e: e.sort_order)
        return found

    def save_errand(self, errand: Errand) -> None:
        self._errands[errand.id] = errand

    def delete_errand(self, errand_id: ErrandId) -> None:
        self._errands.pop(errand_id, None)

    def list_inventory_tasks(self) -> list[Task]:
        items = [
            t
            for t in self._tasks.values()
            if t.completed_at is None
            and t.current_scheduled_date is None
            and t.discarded_at is None
        ]
        items.sort(
            key=lambda t: (t.created_at, self._task_order.get(t.id, 0)),
            reverse=True,
        )
        return items

    def list_scheduled_after(self, today: CalendarDate) -> list[Task]:
        items = [
            t
            for t in self._tasks.values()
            if t.completed_at is None
            and t.current_scheduled_date is not None
            and t.current_scheduled_date > today
        ]
        items.sort(key=lambda t: (t.current_scheduled_date or "", t.title))
        return items

    def list_errands_after(self, today: CalendarDate) -> list[Errand]:
        items = [
            item for item in self._errands.values() if item.day_date > today
        ]
        items.sort(key=lambda item: (item.day_date, item.sort_order, item.id))
        return items

    def get_recurrence(self, series_id: str) -> RecurrenceSeries | None:
        return self._recurrences.get(series_id)

    def list_recurrences(self) -> list[RecurrenceSeries]:
        items = [
            item for item in self._recurrences.values() if item.deleted_at is None
        ]
        items.sort(key=lambda item: (item.state != "active", item.created_at, item.id))
        return items

    def save_recurrence(self, series: RecurrenceSeries) -> None:
        self._recurrences[series.id] = series

    def get_occurrence(
        self, series_id: str, occurrence_date: CalendarDate
    ) -> RecurrenceOccurrence | None:
        return self._occurrences.get((series_id, occurrence_date))

    def save_occurrence(self, occurrence: RecurrenceOccurrence) -> None:
        self._occurrences[(occurrence.series_id, occurrence.occurrence_date)] = occurrence

    def get_planned_at(self, day: CalendarDate) -> str | None:
        return self._planned.get(day)

    def set_day_planned(self, day: CalendarDate, planned_at: str) -> None:
        self._planned[day] = planned_at

    def is_proven_empty(self) -> bool:
        return (
            not self._days
            and not self._entries
            and not self._errands
            and not self._recurrences
        )

    def earliest_relevant_date(self) -> CalendarDate | None:
        dates: list[CalendarDate] = []
        dates.extend(self._days)
        dates.extend(day for day, _ in self._entries)
        dates.extend(errand.day_date for errand in self._errands.values())
        dates.extend(
            task.current_scheduled_date
            for task in self._tasks.values()
            if task.current_scheduled_date is not None
        )
        dates.extend(
            series.schedule_from
            for series in self._recurrences.values()
            if series.deleted_at is None
        )
        return min(dates) if dates else None


def reject_second_open_schedule(uow: UnitOfWork, entry: DayTaskEntry) -> None:
    """One open-day projection at a time; sealed snapshots may remain."""
    for existing in uow.list_entries_for_task(entry.task_id):
        if existing.day_date == entry.day_date:
            continue
        rec = uow.get_day(existing.day_date)
        if rec is None or rec.status == "open":
            raise Conflict("同一任务不能同时排到两天")
