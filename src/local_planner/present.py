"""CamelCase JSON views shared by HTTP and CLI. today is always the caller's txn value."""

from __future__ import annotations

from typing import Any

from local_planner.clock import Clock
from local_planner.agent_contract import capabilities_payload
from local_planner.domain.errors import ValidationError
from local_planner.domain.models import (
    DayPlan,
    InventoryItem,
    PlanningView,
    RecurrenceSeries,
    add_calendar_days,
    is_writable,
    parse_calendar_date,
)
from local_planner.domain.recurrence import mask_to_weekdays, recurrence_matches
from local_planner.domain.settlement import inclusive_range
from local_planner.domain.store import UnitOfWork
from local_planner.domain.ordering import ordered_items


def day_plan_payload(plan: DayPlan, today: str) -> dict[str, Any]:
    todos = ordered_items(plan.todos, manual=plan.manual_todo_order)
    errands = ordered_items(plan.errands, manual=plan.manual_errand_order)
    payload = {
        "date": plan.date,
        "manualTodoOrder": plan.manual_todo_order,
        "manualErrandOrder": plan.manual_errand_order,
        "serverToday": today,
        "isToday": plan.date == today,
        "isPast": plan.date < today,
        "isFuture": plan.date > today,
        "writable": is_writable(plan, today),
        "status": plan.status,
        "todos": [
            {
                "taskId": item.task_id,
                "title": item.title_snapshot,
                "notes": item.notes_snapshot,
                "completedOnDay": item.completed_on_day,
                "sortOrder": item.sort_order,
                "startClock": item.start_clock,
                "endClock": item.end_clock,
                "seriesId": item.series_id,
                "occurrenceDate": item.occurrence_date,
                "goalId": item.goal_id_snapshot,
                "goalTitle": item.goal_title_snapshot,
                "phaseId": item.phase_id_snapshot,
                "phaseTitle": item.phase_title_snapshot,
                "recurrence": _recurrence_origin(
                    item.series_id, item.occurrence_date
                ),
            }
            for item in todos
        ],
        "errands": [
            {
                "id": item.id,
                "title": item.title,
                "notes": item.notes,
                "status": item.status,
                "sortOrder": item.sort_order,
                "startClock": item.start_clock,
                "endClock": item.end_clock,
                "seriesId": item.series_id,
                "occurrenceDate": item.occurrence_date,
                "recurrence": _recurrence_origin(
                    item.series_id, item.occurrence_date
                ),
            }
            for item in errands
        ],
    }
    return payload


def _goal_labels(
    uow: UnitOfWork | None, goal_id: str | None, phase_id: str | None
) -> tuple[str | None, str | None]:
    if uow is None or goal_id is None:
        return None, None
    goal = uow.get_goal(goal_id)
    phase = uow.get_phase(phase_id) if phase_id is not None else None
    return (
        goal.title if goal is not None else None,
        phase.title if phase is not None and phase.goal_id == goal_id else None,
    )


def inventory_item_payload(
    item: InventoryItem, uow: UnitOfWork | None = None
) -> dict[str, Any]:
    goal_title, phase_title = _goal_labels(
        uow, item.task.goal_id, item.task.phase_id
    )
    payload = {
        "taskId": item.task.id,
        "title": item.task.title,
        "notes": item.task.notes,
        "createdAt": item.task.created_at,
        "targetDate": item.task.target_date,
        "seriesId": item.task.series_id,
        "occurrenceDate": item.task.occurrence_date,
        "goalId": item.task.goal_id,
        "goalTitle": goal_title,
        "phaseId": item.task.phase_id,
        "phaseTitle": phase_title,
        "recurrence": _recurrence_origin(
            item.task.series_id, item.task.occurrence_date
        ),
    }
    return payload


def _recurrence_origin(
    series_id: str | None, occurrence_date: str | None
) -> dict[str, str] | None:
    if series_id is None or occurrence_date is None:
        return None
    return {
        "seriesId": series_id,
        "occurrenceDate": occurrence_date,
        "label": "固定周期",
    }


def command_payload(
    result: DayPlan | InventoryItem | None, today: str
) -> dict[str, Any]:
    if result is None:
        return {"ok": True}
    if isinstance(result, DayPlan):
        return day_plan_payload(result, today)
    return inventory_item_payload(result)


def calendar_payload(
    uow: UnitOfWork, start: str, end: str, today: str
) -> dict[str, Any]:
    start_iso = parse_calendar_date(start).isoformat()
    end_iso = parse_calendar_date(end).isoformat()
    if start_iso > end_iso:
        raise ValidationError("日期范围无效")
    days: list[dict[str, Any]] = []
    for day in inclusive_range(start_iso, end_iso):
        todo_count = len(uow.list_entries(day))
        errand_count = len(uow.list_errands(day))
        if todo_count or errand_count:
            days.append(
                {"date": day, "todoCount": todo_count, "errandCount": errand_count}
            )
    return {"today": today, "days": days}


def meta_payload(uow: UnitOfWork, today: str) -> dict[str, Any]:
    return {
        "today": today,
        "timezone": "Asia/Shanghai",
        "lastSettledDate": uow.meta.get("last_settled_date"),
        "inventoryCount": len(uow.list_inventory_tasks()),
        "planningStatus": "ready" if uow.get_planned_at(today) else "unplanned",
    }


def recurrence_payload(
    series: RecurrenceSeries, today: str | None = None
) -> dict[str, Any]:
    return {
        "id": series.id,
        "kind": series.kind,
        "title": series.title,
        "frequency": series.frequency,
        "weekdays": (
            []
            if series.frequency == "daily"
            else mask_to_weekdays(series.weekdays_mask)
        ),
        "startDate": series.start_date,
        "scheduleFrom": series.schedule_from,
        "defaultStartClock": series.default_start_clock,
        "defaultEndClock": series.default_end_clock,
        "state": series.state,
        "createdAt": series.created_at,
        "updatedAt": series.updated_at,
        "pausedAt": series.paused_at,
        "stoppedAt": series.stopped_at,
        "nextOccurrenceDate": _next_occurrence_date(series, today),
    }


def _next_occurrence_date(
    series: RecurrenceSeries, today: str | None
) -> str | None:
    if today is None or series.state != "active":
        return None
    candidate = max(today, series.start_date, series.schedule_from)
    for offset in range(8):
        d = add_calendar_days(candidate, offset)
        if recurrence_matches(series, d):
            return d
    return None


def planning_payload(view: PlanningView, today: str) -> dict[str, Any]:
    return {
        "date": view.date,
        "status": view.status,
        "plannedAt": view.planned_at,
        "day": day_plan_payload(view.day, today),
        "returnedFromYesterday": [
            inventory_item_payload(item) for item in view.returned_from_yesterday
        ],
        "due": [inventory_item_payload(item) for item in view.due],
        "inventory": [inventory_item_payload(item) for item in view.inventory],
        "upcoming": [
            {
                "date": item.date,
                "todoCount": item.todo_count,
                "errandCount": item.errand_count,
                "recurrenceCount": item.recurrence_count,
            }
            for item in view.upcoming
        ],
    }


def context_payload(
    clock: Clock,
    uow: UnitOfWork,
    today: str,
    *,
    surface: str = "today",
    goal_id: str | None = None,
) -> dict[str, Any]:
    from local_planner.domain import commands as cmds
    from local_planner.domain import goals
    from local_planner.domain.errors import NotFound

    plan = cmds.open_day(clock, uow, today)
    day = day_plan_payload(plan, today)
    inventory = cmds.list_inventory(uow)
    ahead = [
        {
            "taskId": task.id,
            "title": task.title,
            "notes": task.notes,
            "date": task.current_scheduled_date,
            "goalId": task.goal_id,
            "phaseId": task.phase_id,
            "goalTitle": _goal_labels(uow, task.goal_id, task.phase_id)[0],
            "phaseTitle": _goal_labels(uow, task.goal_id, task.phase_id)[1],
        }
        for task in uow.list_scheduled_after(today)
    ]
    errands_ahead = [
        {
            "id": item.id,
            "title": item.title,
            "notes": item.notes,
            "date": item.day_date,
            "status": item.status,
            "startClock": item.start_clock,
            "endClock": item.end_clock,
        }
        for item in uow.list_errands_after(today)
    ]
    # Read existing snapshots only: context must not generate future occurrences.
    days_ahead = [day_plan_payload(DayPlan(
        date=record.date, status=record.status, sealed_at=record.sealed_at,
        todos=uow.list_entries(record.date), errands=uow.list_errands(record.date),
        manual_todo_order=record.manual_todo_order,
        manual_errand_order=record.manual_errand_order,
    ), today) for record in uow.list_days_after(today)]
    payload = {
        "today": today,
        "timezone": "Asia/Shanghai",
        "capabilities": capabilities_payload(),
        "manualTodoOrder": day["manualTodoOrder"],
        "manualErrandOrder": day["manualErrandOrder"],
        "writable": day["writable"],
        "status": day["status"],
        "lastSettledDate": uow.meta.get("last_settled_date"),
        "inventoryCount": len(inventory),
        "todos": day["todos"],
        "errands": day["errands"],
        "inventory": [inventory_item_payload(item, uow) for item in inventory],
        "scheduledAhead": ahead,
        "errandsAhead": errands_ahead,
        "daysAhead": days_ahead,
        "recurrences": [
            recurrence_payload(item, today) for item in uow.list_recurrences()
        ],
        "goals": goals.list_goal_payloads(uow),
        "recoveryGeneration": uow.meta.get("recovery_generation"),
        "agentSurface": surface,
    }
    if surface == "goal":
        if goal_id is None:
            raise NotFound("目标页面缺少目标 ID")
        goal = uow.get_goal(goal_id)
        if goal is None:
            raise NotFound("找不到目标")
        payload["goalId"] = goal_id
        payload["currentGoal"] = goals.goal_payload(uow, goal)
    elif goal_id is not None:
        # A goal ID has meaning only for the goal surface.  Keep malformed
        # callers from silently making the ordinary today context authoritative.
        raise ValidationError("当前页面不支持目标 ID")
    return payload
