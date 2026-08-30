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
    Task,
    TaskId,
)


class UnitOfWork(Protocol):
    """Persistence port. Domain never BEGIN/COMMIT; the adapter owns that."""

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


class InMemoryUnitOfWork:
    """Process-local store used until SQLite lands. Same port as persistence."""

    def __init__(self) -> None:
        self._tasks: dict[TaskId, Task] = {}
        self._days: dict[CalendarDate, DayRecord] = {}
        self._entries: dict[tuple[CalendarDate, TaskId], DayTaskEntry] = {}
        self._errands: dict[ErrandId, Errand] = {}
        self._task_seq = 0
        self._task_order: dict[TaskId, int] = {}

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
        self._reject_second_open_schedule(entry)
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
            if t.completed_at is None and t.current_scheduled_date is None
        ]
        items.sort(
            key=lambda t: (t.created_at, self._task_order.get(t.id, 0)),
            reverse=True,
        )
        return items

    def _reject_second_open_schedule(self, entry: DayTaskEntry) -> None:
        for existing in self.list_entries_for_task(entry.task_id):
            if existing.day_date == entry.day_date:
                continue
            rec = self.get_day(existing.day_date)
            if rec is None or rec.status == "open":
                raise Conflict("同一任务不能同时排到两天")
