"""User-facing domain commands. HTTP later adapts these; no FastAPI here."""

from __future__ import annotations

import logging
import uuid
from dataclasses import replace
from datetime import date

from local_planner.clock import Clock, SystemClock, format_utc
from local_planner.domain.errors import Conflict, DaySealed, NotFound
from local_planner.domain.time import validate_clock_pair
from local_planner.domain.models import (
    CalendarDate,
    DayPlan,
    DayRecord,
    DayTaskEntry,
    Errand,
    ErrandId,
    InventoryItem,
    PlanningView,
    RecurrenceSeries,
    Task,
    TaskId,
    UpcomingDay,
    add_calendar_days,
    check_year_cap,
    normalize_title,
    normalize_notes,
    parse_calendar_date,
)
from local_planner.domain.recurrence import (
    UNSET as RECURRENCE_UNSET,
    create_recurrence as _create_recurrence,
    delete_recurrence as _delete_recurrence,
    materialize_occurrences_for_date,
    pause_recurrence as _pause_recurrence,
    recurrence_matches,
    resume_recurrence as _resume_recurrence,
    stop_recurrence as _stop_recurrence,
    update_recurrence as _update_recurrence,
)
from local_planner.domain.seal import seal_day as _seal_day
from local_planner.domain.store import InMemoryUnitOfWork, UnitOfWork

logger = logging.getLogger(__name__)

# SQLite UNIQUE (day_date, sort_order) is not DEFERRABLE; stage through a gap first.
_SORT_ORDER_TEMP = 100_000
UNSET = object()


def _now(clock: Clock) -> str:
    return format_utc(clock.now_utc())


def _incoming_clock(current: str | None, incoming: object) -> str | None:
    if incoming is UNSET:
        return current
    if incoming is None:
        return None
    return str(incoming)


def _new_id() -> str:
    return str(uuid.uuid4())


def _next_sort(items: list[DayTaskEntry] | list[Errand]) -> int:
    if not items:
        return 0
    return max(item.sort_order for item in items) + 1


def is_day_writable(clock: Clock, uow: UnitOfWork, d: CalendarDate) -> bool:
    today = clock.today()
    if parse_calendar_date(d) < date.fromisoformat(today):
        return False
    rec = uow.get_day(d)
    return rec is None or rec.status == "open"


def require_writable_day(clock: Clock, uow: UnitOfWork, d: CalendarDate) -> CalendarDate:
    parsed = parse_calendar_date(d)
    iso = parsed.isoformat()
    check_year_cap(iso, clock.today())
    if iso >= clock.today():
        materialize_occurrences_for_date(clock, uow, iso)
    if not is_day_writable(clock, uow, iso):
        raise DaySealed("这一天已封印，不能改", date=iso)
    return iso


def ensure_open_day(uow: UnitOfWork, d: CalendarDate) -> None:
    rec = uow.get_day(d)
    if rec is None:
        uow.save_day(DayRecord(date=d, status="open", sealed_at=None))


def _require_task(uow: UnitOfWork, task_id: TaskId) -> Task:
    task = uow.get_task(task_id)
    if task is None:
        raise NotFound("找不到该任务")
    return task


def _require_errand(uow: UnitOfWork, errand_id: ErrandId) -> Errand:
    errand = uow.get_errand(errand_id)
    if errand is None:
        raise NotFound("找不到该差事")
    return errand


def _errand_on_writable_day(clock: Clock, uow: UnitOfWork, errand_id: ErrandId) -> Errand:
    errand = _require_errand(uow, errand_id)
    require_writable_day(clock, uow, errand.day_date)
    return errand


def _snapshot_is_sealed(clock: Clock, uow: UnitOfWork, day_date: CalendarDate) -> bool:
    """Past days and sealed rows are immutable, matching `is_day_writable`."""
    return not is_day_writable(clock, uow, day_date)


def _read_day(clock: Clock, uow: UnitOfWork, d: CalendarDate) -> DayPlan:
    parsed = parse_calendar_date(d)
    iso = parsed.isoformat()
    rec = uow.get_day(iso)
    todos = uow.list_entries(iso)
    errands = uow.list_errands(iso)
    if rec is None:
        status = "sealed" if parsed < date.fromisoformat(clock.today()) else "open"
        return DayPlan(date=iso, status=status, sealed_at=None, todos=todos, errands=errands)
    return DayPlan(
        date=iso,
        status=rec.status,
        sealed_at=rec.sealed_at,
        manual_todo_order=rec.manual_todo_order,
        manual_errand_order=rec.manual_errand_order,
        todos=todos,
        errands=errands,
    )


def open_day(clock: Clock, uow: UnitOfWork, d: CalendarDate) -> DayPlan:
    parsed = parse_calendar_date(d)
    iso = parsed.isoformat()
    if iso >= clock.today():
        materialize_occurrences_for_date(clock, uow, iso)
    return _read_day(clock, uow, iso)


def list_inventory(uow: UnitOfWork) -> list[InventoryItem]:
    return [InventoryItem(task=t) for t in uow.list_inventory_tasks()]


def add_todo_on_day(
    clock: Clock,
    uow: UnitOfWork,
    d: CalendarDate,
    title: str,
    start_clock: str | None = None,
    end_clock: str | None = None,
) -> DayPlan:
    iso = require_writable_day(clock, uow, d)
    title = normalize_title(title)
    start_c, end_c = validate_clock_pair(start_clock, end_clock)
    ensure_open_day(uow, iso)
    task = Task(
        id=_new_id(),
        title=title,
        created_at=_now(clock),
        current_scheduled_date=iso,
        completed_at=None,
        completed_on_date=None,
    )
    uow.save_task(task)
    entry = DayTaskEntry(
        day_date=iso,
        task_id=task.id,
        title_snapshot=title,
        sort_order=_next_sort(uow.list_entries(iso)),
        completed_on_day=False,
        start_clock=start_c,
        end_clock=end_c,
    )
    uow.save_entry(entry)
    return open_day(clock, uow, iso)


def add_to_inventory(
    clock: Clock,
    uow: UnitOfWork,
    title: str,
    target_date: str | None = None,
) -> InventoryItem:
    title = normalize_title(title)
    target = None
    if target_date:
        target = parse_calendar_date(target_date).isoformat()
        check_year_cap(target, clock.today())
    task = Task(
        id=_new_id(),
        title=title,
        created_at=_now(clock),
        current_scheduled_date=None,
        completed_at=None,
        completed_on_date=None,
        target_date=target,
    )
    uow.save_task(task)
    return InventoryItem(task=task)


def schedule_to_date(
    clock: Clock, uow: UnitOfWork, task_id: TaskId, d: CalendarDate
) -> DayPlan:
    iso = require_writable_day(clock, uow, d)
    task = _require_task(uow, task_id)
    if task.completed_at is not None:
        raise Conflict("任务已完成")
    current = task.current_scheduled_date
    if current == iso and uow.get_entry(iso, task_id) is not None:
        return open_day(clock, uow, iso)
    if current is not None and current != iso:
        if is_day_writable(clock, uow, current):
            uow.delete_entry(current, task_id)
        else:
            logger.error(
                "current_scheduled_date points at sealed/past day task_id=%s date=%s",
                task_id,
                current,
            )
            raise Conflict("排期指向已封印日")
    ensure_open_day(uow, iso)
    uow.save_task(replace(task, current_scheduled_date=iso))
    existing = uow.get_entry(iso, task_id)
    if existing is None:
        uow.save_entry(
            DayTaskEntry(
                day_date=iso,
                task_id=task_id,
                title_snapshot=task.title,
                notes_snapshot=task.notes,
                sort_order=_next_sort(uow.list_entries(iso)),
                completed_on_day=False,
                series_id=task.series_id,
                occurrence_date=task.occurrence_date,
            )
        )
    return open_day(clock, uow, iso)


def unschedule(clock: Clock, uow: UnitOfWork, task_id: TaskId) -> InventoryItem:
    task = _require_task(uow, task_id)
    if task.completed_at is not None:
        raise Conflict("任务已完成")
    current = task.current_scheduled_date
    if current is None:
        raise Conflict("任务未排期")
    if not is_day_writable(clock, uow, current):
        raise DaySealed("这一天已封印，不能改", date=current)
    uow.delete_entry(current, task_id)
    updated = replace(task, current_scheduled_date=None)
    uow.save_task(updated)
    return InventoryItem(task=updated)


def complete_inventory_task(clock: Clock, uow: UnitOfWork, task_id: TaskId) -> DayPlan:
    """Complete an inventory task today, preserving the normal completion history."""
    task = _require_task(uow, task_id)
    if task.completed_at is not None or task.current_scheduled_date is not None:
        raise Conflict("任务已完成或已排期，请刷新 To Do")
    today = clock.today()
    schedule_to_date(clock, uow, task_id, today)
    return complete_task_on_day(clock, uow, task_id, today)


def complete_task_on_day(
    clock: Clock, uow: UnitOfWork, task_id: TaskId, d: CalendarDate
) -> DayPlan:
    iso = require_writable_day(clock, uow, d)
    task = _require_task(uow, task_id)
    entry = uow.get_entry(iso, task_id)
    if entry is None:
        raise NotFound("这一天没有该任务")
    if entry.completed_on_day:
        raise Conflict("任务当天已勾选")
    if task.completed_at is not None:
        raise Conflict("任务已完成")
    if task.current_scheduled_date != iso:
        raise Conflict("任务未排在这一天")
    uow.save_entry(replace(entry, completed_on_day=True))
    uow.save_task(
        replace(
            task,
            current_scheduled_date=None,
            completed_at=_now(clock),
            completed_on_date=iso,
        )
    )
    return open_day(clock, uow, iso)


def uncomplete_task_on_day(
    clock: Clock, uow: UnitOfWork, task_id: TaskId, d: CalendarDate
) -> DayPlan:
    iso = require_writable_day(clock, uow, d)
    task = _require_task(uow, task_id)
    entry = uow.get_entry(iso, task_id)
    if entry is None:
        raise NotFound("这一天没有该任务")
    if not entry.completed_on_day:
        raise Conflict("任务当天未勾选")
    if task.completed_at is None or task.completed_on_date != iso:
        raise Conflict("任务不是在这一天完成的")
    uow.save_entry(replace(entry, completed_on_day=False))
    uow.save_task(
        replace(
            task,
            current_scheduled_date=iso,
            completed_at=None,
            completed_on_date=None,
        )
    )
    return open_day(clock, uow, iso)


def add_errand(
    clock: Clock,
    uow: UnitOfWork,
    d: CalendarDate,
    title: str,
    start_clock: str | None = None,
    end_clock: str | None = None,
) -> DayPlan:
    iso = require_writable_day(clock, uow, d)
    title = normalize_title(title)
    start_c, end_c = validate_clock_pair(start_clock, end_clock)
    ensure_open_day(uow, iso)
    errand = Errand(
        id=_new_id(),
        day_date=iso,
        title=title,
        sort_order=_next_sort(uow.list_errands(iso)),
        status="open",
        completed_at=None,
        start_clock=start_c,
        end_clock=end_c,
    )
    uow.save_errand(errand)
    return open_day(clock, uow, iso)


def complete_errand(clock: Clock, uow: UnitOfWork, errand_id: ErrandId) -> DayPlan:
    errand = _errand_on_writable_day(clock, uow, errand_id)
    if errand.status != "open":
        raise Conflict("差事无法勾选")
    uow.save_errand(replace(errand, status="completed", completed_at=_now(clock)))
    return open_day(clock, uow, errand.day_date)


def uncomplete_errand(clock: Clock, uow: UnitOfWork, errand_id: ErrandId) -> DayPlan:
    errand = _require_errand(uow, errand_id)
    if errand.status == "expired":
        raise Conflict("已作废的差事不能恢复")
    require_writable_day(clock, uow, errand.day_date)
    if errand.status != "completed":
        raise Conflict("差事未勾选")
    uow.save_errand(replace(errand, status="open", completed_at=None))
    return open_day(clock, uow, errand.day_date)


def delete_errand(clock: Clock, uow: UnitOfWork, errand_id: ErrandId) -> DayPlan:
    errand = _errand_on_writable_day(clock, uow, errand_id)
    if errand.status not in ("open", "completed"):
        raise Conflict("已作废的差事不能改")
    day = errand.day_date
    uow.delete_errand(errand_id)
    return open_day(clock, uow, day)


def rename_errand(
    clock: Clock, uow: UnitOfWork, errand_id: ErrandId, title: str
) -> DayPlan:
    errand = _errand_on_writable_day(clock, uow, errand_id)
    title = normalize_title(title)
    uow.save_errand(replace(errand, title=title))
    return open_day(clock, uow, errand.day_date)


def rename_task(
    clock: Clock, uow: UnitOfWork, task_id: TaskId, title: str
) -> DayPlan | InventoryItem:
    task = _require_task(uow, task_id)
    title = normalize_title(title)
    updated = replace(task, title=title)
    uow.save_task(updated)
    for entry in uow.list_entries_for_task(task_id):
        if _snapshot_is_sealed(clock, uow, entry.day_date):
            continue
        uow.save_entry(replace(entry, title_snapshot=title))
    if updated.current_scheduled_date is not None:
        return open_day(clock, uow, updated.current_scheduled_date)
    return InventoryItem(task=updated)


def edit_details(
    clock: Clock, uow: UnitOfWork, kind: str, item_id: str,
    title: str, notes: str, expected_title: str, expected_notes: str,
) -> DayPlan | InventoryItem:
    """Atomic editing with stale-draft protection; sealed snapshots stay untouched."""
    title, notes = normalize_title(title), normalize_notes(notes)
    if kind == "errand":
        item = _errand_on_writable_day(clock, uow, item_id)
        if (item.title, item.notes) != (expected_title, expected_notes):
            raise Conflict("事项已在别处修改。请保留草稿，关闭后重新打开核对。")
        uow.save_errand(replace(item, title=title, notes=notes))
        return open_day(clock, uow, item.day_date)
    task = _require_task(uow, item_id)
    if task.discarded_at is not None:
        raise NotFound("事项已删除")
    edit_date = task.current_scheduled_date or task.completed_on_date
    if edit_date is not None:
        require_writable_day(clock, uow, edit_date)
    if (task.title, task.notes) != (expected_title, expected_notes):
        raise Conflict("事项已在别处修改。请保留草稿，关闭后重新打开核对。")
    updated = replace(task, title=title, notes=notes)
    uow.save_task(updated)
    for entry in uow.list_entries_for_task(item_id):
        if not _snapshot_is_sealed(clock, uow, entry.day_date):
            uow.save_entry(replace(entry, title_snapshot=title, notes_snapshot=notes))
    if edit_date is not None:
        return open_day(clock, uow, edit_date)
    return InventoryItem(task=updated)


def delete_task(clock: Clock, uow: UnitOfWork, task_id: TaskId) -> None:
    task = _require_task(uow, task_id)
    entries = uow.list_entries_for_task(task_id)
    in_todo = task.completed_at is None and task.current_scheduled_date is None
    if in_todo:
        for entry in entries:
            if not _snapshot_is_sealed(clock, uow, entry.day_date):
                uow.delete_entry(entry.day_date, task_id)
        leftover = uow.list_entries_for_task(task_id)
        if leftover:
            uow.save_task(replace(task, discarded_at=_now(clock)))
        else:
            uow.delete_task_row(task_id)
        return
    for entry in entries:
        if _snapshot_is_sealed(clock, uow, entry.day_date):
            raise Conflict("过去的某一天还记着它，不能删")
    for entry in entries:
        uow.delete_entry(entry.day_date, task_id)
    uow.delete_task_row(task_id)


def reorder_todos(
    clock: Clock, uow: UnitOfWork, d: CalendarDate, task_ids: list[TaskId],
    *, manual: bool = True,
) -> DayPlan:
    iso = require_writable_day(clock, uow, d)
    current = [e.task_id for e in uow.list_entries(iso)]
    if set(task_ids) != set(current) or len(task_ids) != len(current):
        raise Conflict("排序与当天条目不一致")
    staged: list[tuple[int, DayTaskEntry]] = []
    for i, task_id in enumerate(task_ids):
        entry = uow.get_entry(iso, task_id)
        if entry is None:
            raise Conflict("排序与当天条目不一致")
        staged.append((i, entry))
    for i, entry in staged:
        uow.save_entry(replace(entry, sort_order=i + _SORT_ORDER_TEMP))
    for i, entry in staged:
        uow.save_entry(replace(entry, sort_order=i))
    ensure_open_day(uow, iso)
    uow.save_day(replace(uow.get_day(iso), manual_todo_order=manual))
    return open_day(clock, uow, iso)


def reorder_errands(
    clock: Clock, uow: UnitOfWork, d: CalendarDate, errand_ids: list[ErrandId],
    *, manual: bool = True,
) -> DayPlan:
    iso = require_writable_day(clock, uow, d)
    current = [e.id for e in uow.list_errands(iso)]
    if set(errand_ids) != set(current) or len(errand_ids) != len(current):
        raise Conflict("排序与当天条目不一致")
    staged: list[tuple[int, Errand]] = []
    for i, errand_id in enumerate(errand_ids):
        errand = uow.get_errand(errand_id)
        if errand is None:
            raise Conflict("排序与当天条目不一致")
        staged.append((i, errand))
    for i, errand in staged:
        uow.save_errand(replace(errand, sort_order=i + _SORT_ORDER_TEMP))
    for i, errand in staged:
        uow.save_errand(replace(errand, sort_order=i))
    ensure_open_day(uow, iso)
    uow.save_day(replace(uow.get_day(iso), manual_errand_order=manual))
    return open_day(clock, uow, iso)


def set_target_date(
    clock: Clock, uow: UnitOfWork, task_id: TaskId, raw_date: str | None
) -> InventoryItem | DayPlan:
    task = _require_task(uow, task_id)
    if raw_date is None or not str(raw_date).strip():
        updated = replace(task, target_date=None)
    else:
        iso = parse_calendar_date(str(raw_date)).isoformat()
        check_year_cap(iso, clock.today())
        updated = replace(task, target_date=iso)
    uow.save_task(updated)
    if updated.current_scheduled_date:
        return open_day(clock, uow, updated.current_scheduled_date)
    return InventoryItem(task=updated)


def set_plan_clocks(
    clock: Clock,
    uow: UnitOfWork,
    d: CalendarDate,
    task_id: TaskId,
    start_clock: str | None | object = UNSET,
    end_clock: str | None | object = UNSET,
) -> DayPlan:
    iso = require_writable_day(clock, uow, d)
    entry = uow.get_entry(iso, task_id)
    if entry is None:
        raise NotFound("这一天没有该任务")
    start_c, end_c = validate_clock_pair(
        _incoming_clock(entry.start_clock, start_clock),
        _incoming_clock(entry.end_clock, end_clock),
    )
    uow.save_entry(replace(entry, start_clock=start_c, end_clock=end_c))
    return open_day(clock, uow, iso)


def set_errand_clocks(
    clock: Clock,
    uow: UnitOfWork,
    errand_id: ErrandId,
    start_clock: str | None | object = UNSET,
    end_clock: str | None | object = UNSET,
) -> DayPlan:
    errand = _errand_on_writable_day(clock, uow, errand_id)
    start_c, end_c = validate_clock_pair(
        _incoming_clock(errand.start_clock, start_clock),
        _incoming_clock(errand.end_clock, end_clock),
    )
    uow.save_errand(replace(errand, start_clock=start_c, end_clock=end_c))
    return open_day(clock, uow, errand.day_date)


def create_recurrence(
    clock: Clock,
    uow: UnitOfWork,
    *,
    kind: str,
    title: str,
    frequency: str,
    weekdays: list[str] | None,
    start_date: str,
    default_start_clock: str | None = None,
    default_end_clock: str | None = None,
) -> RecurrenceSeries:
    return _create_recurrence(
        clock,
        uow,
        kind=kind,
        title=title,
        frequency=frequency,
        weekdays=weekdays,
        start_date=start_date,
        default_start_clock=default_start_clock,
        default_end_clock=default_end_clock,
    )


def update_recurrence(
    clock: Clock,
    uow: UnitOfWork,
    series_id: str,
    *,
    title: str | object = RECURRENCE_UNSET,
    frequency: str | object = RECURRENCE_UNSET,
    weekdays: list[str] | None | object = RECURRENCE_UNSET,
    start_date: str | object = RECURRENCE_UNSET,
    default_start_clock: str | None | object = RECURRENCE_UNSET,
    default_end_clock: str | None | object = RECURRENCE_UNSET,
) -> RecurrenceSeries:
    return _update_recurrence(
        clock,
        uow,
        series_id,
        title=title,
        frequency=frequency,
        weekdays=weekdays,
        start_date=start_date,
        default_start_clock=default_start_clock,
        default_end_clock=default_end_clock,
    )


def list_recurrences(uow: UnitOfWork) -> list[RecurrenceSeries]:
    return uow.list_recurrences()


def pause_recurrence(
    clock: Clock, uow: UnitOfWork, series_id: str
) -> RecurrenceSeries:
    return _pause_recurrence(clock, uow, series_id)


def resume_recurrence(
    clock: Clock, uow: UnitOfWork, series_id: str
) -> RecurrenceSeries:
    return _resume_recurrence(clock, uow, series_id)


def stop_recurrence(
    clock: Clock, uow: UnitOfWork, series_id: str
) -> RecurrenceSeries:
    return _stop_recurrence(clock, uow, series_id)


def delete_recurrence(clock: Clock, uow: UnitOfWork, series_id: str) -> None:
    _delete_recurrence(clock, uow, series_id)


def open_planning_today(clock: Clock, uow: UnitOfWork) -> PlanningView:
    today = clock.today()
    plan = open_day(clock, uow, today)
    inventory = list_inventory(uow)
    inventory_by_id = {item.task.id: item for item in inventory}
    yesterday = add_calendar_days(today, -1)
    returned_ids = {
        entry.task_id
        for entry in uow.list_entries(yesterday)
        if not entry.completed_on_day and entry.task_id in inventory_by_id
    }
    returned = [item for item in inventory if item.task.id in returned_ids]
    due_ids = {
        item.task.id
        for item in inventory
        if item.task.id not in returned_ids
        and item.task.target_date is not None
        and item.task.target_date <= today
    }
    due = [
        item
        for item in inventory
        if item.task.id in due_ids
    ]
    remaining_inventory = [
        item
        for item in inventory
        if item.task.id not in returned_ids and item.task.id not in due_ids
    ]
    upcoming: list[UpcomingDay] = []
    for offset in range(1, 8):
        d = add_calendar_days(today, offset)
        entries = uow.list_entries(d)
        errands = uow.list_errands(d)
        todo_count = sum(1 for item in entries if item.series_id is None)
        errand_count = sum(1 for item in errands if item.series_id is None)
        recurrence_count = sum(1 for item in entries if item.series_id is not None)
        recurrence_count += sum(
            1 for item in errands if item.series_id is not None
        )
        for series in uow.list_recurrences():
            if recurrence_matches(series, d) and uow.get_occurrence(series.id, d) is None:
                recurrence_count += 1
        if todo_count or errand_count or recurrence_count:
            upcoming.append(
                UpcomingDay(
                    date=d,
                    todo_count=todo_count,
                    errand_count=errand_count,
                    recurrence_count=recurrence_count,
                )
            )
    planned_at = uow.get_planned_at(today)
    return PlanningView(
        date=today,
        status="ready" if planned_at is not None else "unplanned",
        planned_at=planned_at,
        day=plan,
        returned_from_yesterday=returned,
        due=due,
        inventory=remaining_inventory,
        upcoming=upcoming,
    )


def complete_planning_today(clock: Clock, uow: UnitOfWork) -> PlanningView:
    today = require_writable_day(clock, uow, clock.today())
    ensure_open_day(uow, today)
    if uow.get_planned_at(today) is None:
        uow.set_day_planned(today, _now(clock))
    return open_planning_today(clock, uow)


class Planner:
    """Convenience wrapper for tests and later adapters."""

    def __init__(
        self, clock: Clock | None = None, uow: UnitOfWork | None = None
    ) -> None:
        self.clock: Clock = clock or SystemClock()
        self.uow: UnitOfWork = uow or InMemoryUnitOfWork()

    def open_day(self, d: CalendarDate) -> DayPlan:
        return open_day(self.clock, self.uow, d)

    def list_inventory(self) -> list[InventoryItem]:
        return list_inventory(self.uow)

    def add_todo_on_day(
        self,
        d: CalendarDate,
        title: str,
        start_clock: str | None = None,
        end_clock: str | None = None,
    ) -> DayPlan:
        return add_todo_on_day(
            self.clock, self.uow, d, title, start_clock, end_clock
        )

    def add_to_inventory(
        self, title: str, target_date: str | None = None
    ) -> InventoryItem:
        return add_to_inventory(self.clock, self.uow, title, target_date)

    def schedule_to_date(self, task_id: TaskId, d: CalendarDate) -> DayPlan:
        return schedule_to_date(self.clock, self.uow, task_id, d)

    def unschedule(self, task_id: TaskId) -> InventoryItem:
        return unschedule(self.clock, self.uow, task_id)

    def complete_task_on_day(self, task_id: TaskId, d: CalendarDate) -> DayPlan:
        return complete_task_on_day(self.clock, self.uow, task_id, d)

    def uncomplete_task_on_day(self, task_id: TaskId, d: CalendarDate) -> DayPlan:
        return uncomplete_task_on_day(self.clock, self.uow, task_id, d)

    def add_errand(
        self,
        d: CalendarDate,
        title: str,
        start_clock: str | None = None,
        end_clock: str | None = None,
    ) -> DayPlan:
        return add_errand(self.clock, self.uow, d, title, start_clock, end_clock)

    def complete_errand(self, errand_id: ErrandId) -> DayPlan:
        return complete_errand(self.clock, self.uow, errand_id)

    def uncomplete_errand(self, errand_id: ErrandId) -> DayPlan:
        return uncomplete_errand(self.clock, self.uow, errand_id)

    def delete_errand(self, errand_id: ErrandId) -> DayPlan:
        return delete_errand(self.clock, self.uow, errand_id)

    def rename_errand(self, errand_id: ErrandId, title: str) -> DayPlan:
        return rename_errand(self.clock, self.uow, errand_id, title)

    def rename_task(self, task_id: TaskId, title: str) -> DayPlan | InventoryItem:
        return rename_task(self.clock, self.uow, task_id, title)

    def delete_task(self, task_id: TaskId) -> None:
        delete_task(self.clock, self.uow, task_id)

    def reorder_todos(self, d: CalendarDate, task_ids: list[TaskId]) -> DayPlan:
        return reorder_todos(self.clock, self.uow, d, task_ids)

    def reorder_errands(self, d: CalendarDate, errand_ids: list[ErrandId]) -> DayPlan:
        return reorder_errands(self.clock, self.uow, d, errand_ids)

    def seal_day(self, d: CalendarDate) -> None:
        _seal_day(self.clock, self.uow, d)

    def get_task(self, task_id: TaskId) -> Task:
        return _require_task(self.uow, task_id)
