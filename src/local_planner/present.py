"""CamelCase JSON views shared by HTTP and CLI. today is always the caller's txn value."""

from __future__ import annotations

from typing import Any

from local_planner.domain.errors import ValidationError
from local_planner.domain.models import DayPlan, InventoryItem, is_writable, parse_calendar_date
from local_planner.domain.settlement import inclusive_range
from local_planner.domain.store import UnitOfWork


def day_plan_payload(plan: DayPlan, today: str) -> dict[str, Any]:
    return {
        "date": plan.date,
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
                "completedOnDay": item.completed_on_day,
                "sortOrder": item.sort_order,
            }
            for item in plan.todos
        ],
        "errands": [
            {
                "id": item.id,
                "title": item.title,
                "status": item.status,
                "sortOrder": item.sort_order,
            }
            for item in plan.errands
        ],
    }


def inventory_item_payload(item: InventoryItem) -> dict[str, Any]:
    return {
        "taskId": item.task.id,
        "title": item.task.title,
        "createdAt": item.task.created_at,
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
    }
