"""Undo one deletion without rewinding unrelated changes or sealed history."""

from dataclasses import dataclass, replace
from typing import Literal

from local_planner.clock import Clock
from local_planner.domain import commands
from local_planner.domain.errors import Conflict, NotFound
from local_planner.domain.models import DayTaskEntry, Errand, RecurrenceSeries, Task
from local_planner.domain.store import UnitOfWork


@dataclass(frozen=True)
class DeletedItem:
    kind: Literal["task", "errand", "recurrence"]
    before: Task | Errand | RecurrenceSeries
    after: Task | Errand | RecurrenceSeries | None
    entries: tuple[DayTaskEntry, ...] = ()


def delete_with_undo(clock: Clock, uow: UnitOfWork, kind: str, entity_id: str) -> DeletedItem:
    if kind == "task":
        before = uow.get_task(entity_id)
        if before is None or before.discarded_at is not None:
            raise NotFound("找不到该事项")
        entries = tuple(uow.list_entries_for_task(entity_id))
        commands.delete_task(clock, uow, entity_id)
        removed = tuple(e for e in entries if uow.get_entry(e.day_date, entity_id) is None)
        return DeletedItem("task", before, uow.get_task(entity_id), removed)
    if kind == "errand":
        before = uow.get_errand(entity_id)
        if before is None:
            raise NotFound("找不到该事项")
        commands.delete_errand(clock, uow, entity_id)
        return DeletedItem("errand", before, None)
    before = uow.get_recurrence(entity_id)
    if before is None or before.deleted_at is not None:
        raise NotFound("找不到该定期事项")
    commands.delete_recurrence(clock, uow, entity_id)
    return DeletedItem("recurrence", before, uow.get_recurrence(entity_id))


def undo_delete(clock: Clock, uow: UnitOfWork, change: DeletedItem) -> None:
    before = change.before
    if isinstance(before, Task):
        if uow.get_task(before.id) != change.after:
            raise Conflict("事项已经发生变化，无法撤销这次删除")
        # Validate every date before writing anything. Never rewrite past snapshots.
        for entry in change.entries:
            commands.require_writable_day(clock, uow, entry.day_date)
            if uow.get_entry(entry.day_date, before.id) is not None:
                raise Conflict("事项已经恢复，请刷新页面")
        uow.save_task(before)
        for entry in change.entries:
            entries = uow.list_entries(entry.day_date)
            if any(e.sort_order == entry.sort_order for e in entries):
                entry = replace(entry, sort_order=max(e.sort_order for e in entries) + 1)
            uow.save_entry(entry)
    elif isinstance(before, Errand):
        commands.require_writable_day(clock, uow, before.day_date)
        if uow.get_errand(before.id) is not None:
            raise Conflict("事项已经恢复，请刷新页面")
        entries = uow.list_errands(before.day_date)
        if any(e.sort_order == before.sort_order for e in entries):
            before = replace(before, sort_order=max(e.sort_order for e in entries) + 1)
        uow.save_errand(before)
    else:
        if uow.get_recurrence(before.id) != change.after:
            raise Conflict("定期事项已经变化，无法撤销这次删除")
        # A deleted series was stopped; undo restores that stopped state.
        uow.save_recurrence(before)
