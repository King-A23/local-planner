"""Search existing unfinished items, using the same domain visibility as the lists."""
from __future__ import annotations

from local_planner.clock import Clock
from local_planner.domain.commands import is_day_writable, open_day
from local_planner.domain.models import add_calendar_days
from local_planner.domain.errors import ValidationError
from local_planner.domain.store import UnitOfWork


def search_items(clock: Clock, uow: UnitOfWork, query: str) -> dict:
    if len(query) > 200:
        raise ValidationError("搜索内容不能超过 200 字")
    today = clock.today()
    terms = query.casefold().split()
    if not terms:
        return {"items": [], "total": 0, "today": today}
    open_day(clock, uow, today)
    yesterday = add_calendar_days(today, -1)
    candidates = []
    for task in uow.list_inventory_tasks() + uow.list_scheduled_after(yesterday):
        day = task.current_scheduled_date
        if task.discarded_at is not None or (day and not is_day_writable(clock, uow, day)):
            continue
        candidates.append({"id": task.id, "kind": "task", "title": task.title,
                           "notes": task.notes, "date": day})
    for item in uow.list_errands_after(yesterday):
        if item.status == "open" and is_day_writable(clock, uow, item.day_date):
            candidates.append({"id": item.id, "kind": "errand", "title": item.title,
                               "notes": item.notes, "date": item.day_date})
    matches = [item for item in candidates
               if all(term in (item["title"] + "\n" + item["notes"]).casefold() for term in terms)]
    matches.sort(key=lambda item: (
        not item["title"].casefold().startswith(query.strip().casefold()),
        0 if item["date"] == today else 1 if item["date"] is None else 2,
        item["date"] or "", item["title"].casefold(), item["id"],
    ))
    return {"items": matches[:50], "total": len(matches), "today": today}
