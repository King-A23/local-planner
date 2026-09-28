"""Semantic receipts derived from normalized planner context snapshots.

The launcher is an external process and may execute more than one CLI command.  Its
stdout is therefore not a reliable audit trail.  This module compares the stable
entity ids in two ``context_payload`` values and reports only planner semantics.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal, Mapping

Context = Mapping[str, Any]
Location = Literal["plan", "todo", "scheduled"]


@dataclass(frozen=True)
class _TaskState:
    task_id: str
    title: str
    location: Location
    date: str | None
    completed: bool | None = None
    start_clock: str | None = None
    end_clock: str | None = None
    target_date: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class _ErrandState:
    errand_id: str
    title: str
    status: str
    date: str | None
    start_clock: str | None = None
    end_clock: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class _RecurrenceState:
    series_id: str
    title: str
    state: str
    kind: str
    frequency: str
    weekdays: tuple[str, ...]
    start_date: str | None
    start_clock: str | None
    end_clock: str | None


_TYPE_ORDER = {
    "recurrence_created": -5,
    "recurrence_updated": -4,
    "recurrence_paused": -3,
    "recurrence_resumed": -2,
    "recurrence_stopped": -1,
    "recurrence_deleted": 0,
    "goal_created": 16,
    "goal_updated": 17,
    "goal_paused": 18,
    "goal_resumed": 19,
    "goal_ended": 20,
    "phase_added": 21,
    "phase_updated": 22,
    "phase_order_changed": 23,
    "task_linked_goal": 24,
    "task_unlinked_goal": 25,
    "goal_next_changed": 26,
    "goal_focus_changed": 27,
    "plan_added": 1,
    "errand_added": 2,
    "todo_added": 3,
    "todo_to_today": 4,
    "todo_scheduled": 5,
    "moved_to_todo": 6,
    "rescheduled": 7,
    "completed": 8,
    "completion_undone": 9,
    "renamed": 10,
    "clock_changed": 11,
    "target_date_changed": 12,
    "notes_changed": 13,
    "order_changed": 14,
    "deleted": 15,
}

_SUMMARY_LABELS = {
    "recurrence_created": "新增定期事项",
    "recurrence_updated": "更新定期事项",
    "recurrence_paused": "暂停定期事项",
    "recurrence_resumed": "恢复定期事项",
    "recurrence_stopped": "停止定期事项",
    "recurrence_deleted": "删除定期事项",
    "goal_created": "新增目标",
    "goal_updated": "更新目标",
    "goal_paused": "暂停目标",
    "goal_resumed": "恢复目标",
    "goal_ended": "结束目标",
    "phase_added": "新增阶段",
    "phase_updated": "更新阶段",
    "phase_order_changed": "调整阶段顺序",
    "task_linked_goal": "关联目标事项",
    "task_unlinked_goal": "解除目标事项",
    "goal_next_changed": "更新下一步",
    "goal_focus_changed": "更新当前阶段",
    "plan_added": "新增 Plan",
    "errand_added": "新增 Errand",
    "todo_added": "新增 To Do",
    "todo_to_today": "To Do 加入今天",
    "todo_scheduled": "To Do 排入计划",
    "moved_to_todo": "移回 To Do",
    "rescheduled": "改排",
    "completed": "完成",
    "completion_undone": "取消完成",
    "renamed": "改名",
    "clock_changed": "改时钟",
    "target_date_changed": "改目标日",
    "notes_changed": "更新备注",
    "order_changed": "调整排序",
    "deleted": "删除",
}


def build_agent_receipt(before: Context, after: Context) -> dict[str, Any]:
    """Return a stable JSON-compatible semantic diff of two context payloads.

    Unknown context keys are ignored.  Change order is deterministic by semantic
    type and entity id, so the payload is suitable for API responses and tests.
    """

    before_today = _optional_text(before.get("today"))
    after_today = _optional_text(after.get("today"))
    before_tasks = _task_states(before)
    after_tasks = _task_states(after)
    before_errands = _errand_states(before)
    after_errands = _errand_states(after)
    before_recurrences = _recurrence_states(before)
    after_recurrences = _recurrence_states(after)
    before_goals = _goal_rows(before)
    after_goals = _goal_rows(after)

    changes: list[dict[str, Any]] = []
    for task_id in sorted(set(before_tasks) | set(after_tasks)):
        old = before_tasks.get(task_id)
        new = after_tasks.get(task_id)
        changes.extend(_diff_task(old, new, before_today, after_today))

    for errand_id in sorted(set(before_errands) | set(after_errands)):
        old = before_errands.get(errand_id)
        new = after_errands.get(errand_id)
        changes.extend(_diff_errand(old, new))

    for series_id in sorted(set(before_recurrences) | set(after_recurrences)):
        changes.extend(
            _diff_recurrence(
                before_recurrences.get(series_id),
                after_recurrences.get(series_id),
            )
        )

    for goal_id in sorted(set(before_goals) | set(after_goals)):
        changes.extend(_diff_goal(before_goals.get(goal_id), after_goals.get(goal_id)))

    changes.extend(_diff_orders(before, after))
    changes.sort(
        key=lambda change: (
            _TYPE_ORDER[change["type"]],
            change["entity"],
            change["id"],
        )
    )
    counts = Counter(change["type"] for change in changes)
    stable_counts = {
        change_type: counts[change_type]
        for change_type in _TYPE_ORDER
        if counts[change_type]
    }
    return {
        "summary": _summarize(counts),
        "changed": bool(changes),
        "counts": stable_counts,
        "changes": changes,
    }


def _task_states(context: Context) -> dict[str, _TaskState]:
    today = _optional_text(context.get("today"))
    states: dict[str, _TaskState] = {}
    for row in _rows(context, "todos"):
        task_id = _required_id(row, "taskId")
        states[task_id] = _TaskState(
            task_id=task_id,
            title=_text(row.get("title")),
            location="plan",
            date=today,
            completed=bool(row.get("completedOnDay", False)),
            start_clock=_optional_text(row.get("startClock")),
            end_clock=_optional_text(row.get("endClock")),
            notes=_optional_text(row.get("notes")),
        )
    for row in _rows(context, "inventory"):
        task_id = _required_id(row, "taskId")
        states[task_id] = _TaskState(
            task_id=task_id,
            title=_text(row.get("title")),
            location="todo",
            date=None,
            target_date=_optional_text(row.get("targetDate")),
            notes=_optional_text(row.get("notes")),
        )
    for row in _rows(context, "scheduledAhead"):
        task_id = _required_id(row, "taskId")
        states[task_id] = _TaskState(
            task_id=task_id,
            title=_text(row.get("title")),
            location="scheduled",
            date=_optional_text(row.get("date")),
            notes=_optional_text(row.get("notes")),
        )
    for day in _rows(context, "daysAhead"):
        for row in _rows(day, "todos"):
            task_id = _required_id(row, "taskId")
            states[task_id] = _TaskState(
                task_id=task_id, title=_text(row.get("title")), location="scheduled",
                date=_optional_text(day.get("date")), completed=bool(row.get("completedOnDay", False)),
                start_clock=_optional_text(row.get("startClock")), end_clock=_optional_text(row.get("endClock")),
                notes=_optional_text(row.get("notes")),
            )
    return states


def _errand_states(context: Context) -> dict[str, _ErrandState]:
    today = _optional_text(context.get("today"))
    states: dict[str, _ErrandState] = {}
    for row in _rows(context, "errands"):
        errand_id = _required_id(row, "id")
        states[errand_id] = _ErrandState(
            errand_id=errand_id,
            title=_text(row.get("title")),
            status=_text(row.get("status")) or "open",
            date=today,
            start_clock=_optional_text(row.get("startClock")),
            end_clock=_optional_text(row.get("endClock")),
            notes=_optional_text(row.get("notes")),
        )
    for row in _rows(context, "errandsAhead"):
        errand_id = _required_id(row, "id")
        states[errand_id] = _ErrandState(
            errand_id=errand_id,
            title=_text(row.get("title")),
            status=_text(row.get("status")) or "open",
            date=_optional_text(row.get("date")),
            start_clock=_optional_text(row.get("startClock")),
            end_clock=_optional_text(row.get("endClock")),
            notes=_optional_text(row.get("notes")),
        )
    return states


def _recurrence_states(context: Context) -> dict[str, _RecurrenceState]:
    states: dict[str, _RecurrenceState] = {}
    for row in _rows(context, "recurrences"):
        series_id = _required_id(row, "id")
        states[series_id] = _RecurrenceState(
            series_id=series_id,
            title=_text(row.get("title")),
            state=_text(row.get("state")),
            kind=_text(row.get("kind")),
            frequency=_text(row.get("frequency")),
            weekdays=tuple(str(value) for value in (row.get("weekdays") or [])),
            start_date=_optional_text(row.get("startDate")),
            start_clock=_optional_text(row.get("defaultStartClock")),
            end_clock=_optional_text(row.get("defaultEndClock")),
        )
    return states


def _goal_rows(context: Context) -> dict[str, Mapping[str, Any]]:
    """Read only the canonical list, never the duplicated currentGoal context."""
    return {
        _required_id(row, "id"): row
        for row in _rows(context, "goals")
    }


def _goal_tasks(goal: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        _required_id(row, "taskId"): row
        for row in _rows(goal, "tasks")
    }


def _goal_phases(goal: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        _required_id(row, "id"): row
        for row in _rows(goal, "phases")
    }


def _diff_goal(
    old: Mapping[str, Any] | None, new: Mapping[str, Any] | None
) -> list[dict[str, Any]]:
    if old is None and new is not None:
        return [_change("goal_created", "goal", _required_id(new, "id"), _text(new.get("title")))]
    if old is None or new is None:
        # Goals have no delete operation in this product version.
        return []
    goal_id = _required_id(new, "id")
    title = _text(new.get("title"))
    changes: list[dict[str, Any]] = []
    if (
        _text(old.get("title")), _optional_text(old.get("notes")),
        _optional_text(old.get("horizonText")),
    ) != (
        title, _optional_text(new.get("notes")), _optional_text(new.get("horizonText")),
    ):
        changes.append(_change("goal_updated", "goal", goal_id, title))
    if _text(old.get("state")) != _text(new.get("state")):
        event = {"paused": "goal_paused", "active": "goal_resumed", "ended": "goal_ended"}.get(_text(new.get("state")))
        if event:
            changes.append(_change(event, "goal", goal_id, title))
    if old.get("nextTaskId") != new.get("nextTaskId"):
        changes.append(_change(
            "goal_next_changed", "goal", goal_id, title,
            before=old.get("nextTaskId"), after=new.get("nextTaskId"),
        ))
    if old.get("focusPhaseId") != new.get("focusPhaseId"):
        changes.append(_change(
            "goal_focus_changed", "goal", goal_id, title,
            before=old.get("focusPhaseId"), after=new.get("focusPhaseId"),
        ))

    old_tasks, new_tasks = _goal_tasks(old), _goal_tasks(new)
    for task_id in sorted(set(old_tasks) | set(new_tasks)):
        old_task, new_task = old_tasks.get(task_id), new_tasks.get(task_id)
        if old_task is None and new_task is not None:
            changes.append(_change("task_linked_goal", "goal_task", task_id, _text(new_task.get("title")), goalId=goal_id))
        elif old_task is not None and new_task is None:
            changes.append(_change("task_unlinked_goal", "goal_task", task_id, _text(old_task.get("title")), goalId=goal_id))
        elif old_task is not None and new_task is not None and old_task.get("phaseId") != new_task.get("phaseId"):
            changes.append(_change("task_linked_goal", "goal_task", task_id, _text(new_task.get("title")), goalId=goal_id, beforePhaseId=old_task.get("phaseId"), afterPhaseId=new_task.get("phaseId")))

    old_phases, new_phases = _goal_phases(old), _goal_phases(new)
    for phase_id in sorted(set(old_phases) | set(new_phases)):
        old_phase, new_phase = old_phases.get(phase_id), new_phases.get(phase_id)
        if old_phase is None and new_phase is not None:
            changes.append(_change("phase_added", "phase", phase_id, _text(new_phase.get("title")), goalId=goal_id))
        elif old_phase is not None and new_phase is not None:
            if (
                _text(old_phase.get("title")), _optional_text(old_phase.get("notes")), _text(old_phase.get("status")),
            ) != (
                _text(new_phase.get("title")), _optional_text(new_phase.get("notes")), _text(new_phase.get("status")),
            ):
                changes.append(_change("phase_updated", "phase", phase_id, _text(new_phase.get("title")), goalId=goal_id))
    old_order = [row_id for row_id, _ in sorted(old_phases.items(), key=lambda pair: int(pair[1].get("position", 0)))]
    new_order = [row_id for row_id, _ in sorted(new_phases.items(), key=lambda pair: int(pair[1].get("position", 0)))]
    if old_order != new_order and set(old_order) == set(new_order):
        changes.append(_change("phase_order_changed", "goal", goal_id, title))
    return changes


def _diff_recurrence(
    old: _RecurrenceState | None, new: _RecurrenceState | None
) -> list[dict[str, Any]]:
    if old is None and new is not None:
        return [
            _change(
                "recurrence_created", "recurrence", new.series_id, new.title
            )
        ]
    if old is not None and new is None:
        return [
            _change(
                "recurrence_deleted", "recurrence", old.series_id, old.title
            )
        ]
    if old is None or new is None:
        return []
    changes: list[dict[str, Any]] = []
    old_rule = (
        old.title,
        old.kind,
        old.frequency,
        old.weekdays,
        old.start_date,
        old.start_clock,
        old.end_clock,
    )
    new_rule = (
        new.title,
        new.kind,
        new.frequency,
        new.weekdays,
        new.start_date,
        new.start_clock,
        new.end_clock,
    )
    if old_rule != new_rule:
        changes.append(
            _change(
                "recurrence_updated", "recurrence", new.series_id, new.title
            )
        )
    if old.state != new.state:
        transition = {
            "paused": "recurrence_paused",
            "active": "recurrence_resumed",
            "stopped": "recurrence_stopped",
        }.get(new.state)
        if transition:
            changes.append(
                _change(transition, "recurrence", new.series_id, new.title)
            )
    return changes


def _diff_task(
    old: _TaskState | None,
    new: _TaskState | None,
    before_today: str | None,
    after_today: str | None,
) -> list[dict[str, Any]]:
    if old is None and new is not None:
        if new.location == "todo":
            return [_change("todo_added", "todo", new.task_id, new.title)]
        return [
            _change(
                "plan_added",
                "plan",
                new.task_id,
                new.title,
                date=new.date,
            )
        ]
    if old is not None and new is None:
        return [
            _change(
                "deleted",
                _task_entity(old),
                old.task_id,
                old.title,
                date=old.date,
            )
        ]
    if old is None or new is None:  # pragma: no cover - narrowed above
        return []

    changes: list[dict[str, Any]] = []
    if old.location == "todo" and new.location == "plan" and new.date == after_today:
        changes.append(
            _change(
                "todo_to_today",
                "plan",
                new.task_id,
                new.title,
                toDate=new.date,
            )
        )
    elif old.location == "todo" and new.location == "scheduled":
        changes.append(
            _change(
                "todo_scheduled",
                "plan",
                new.task_id,
                new.title,
                toDate=new.date,
            )
        )
    elif old.location in ("plan", "scheduled") and new.location == "todo":
        changes.append(
            _change(
                "moved_to_todo",
                "todo",
                new.task_id,
                new.title,
                fromDate=old.date,
            )
        )
    elif _is_schedule_move(old, new, before_today, after_today):
        changes.append(
            _change(
                "rescheduled",
                "plan",
                new.task_id,
                new.title,
                fromDate=old.date,
                toDate=new.date,
            )
        )

    if new.completed is not None:
        if old.completed is not True and new.completed is True:
            changes.append(
                _change("completed", "plan", new.task_id, new.title, date=new.date)
            )
        elif old.completed is True and new.completed is False:
            changes.append(
                _change(
                    "completion_undone",
                    "plan",
                    new.task_id,
                    new.title,
                    date=new.date,
                )
            )

    if old.title != new.title:
        changes.append(
            _change(
                "renamed",
                _task_entity(new),
                new.task_id,
                new.title,
                before=old.title,
                after=new.title,
            )
        )

    # Clocks belong to a particular Plan appearance.  Comparing them across an
    # unschedule/reschedule would turn an intentionally hidden value into a false
    # clock edit, so only compare the same visible appearance.
    if (
        old.location == new.location and new.location in ("plan", "scheduled")
        and old.date == new.date
        and (old.start_clock, old.end_clock) != (new.start_clock, new.end_clock)
    ):
        changes.append(
            _change(
                "clock_changed",
                "plan",
                new.task_id,
                new.title,
                before={
                    "startClock": old.start_clock,
                    "endClock": old.end_clock,
                },
                after={
                    "startClock": new.start_clock,
                    "endClock": new.end_clock,
                },
            )
        )

    # targetDate is currently present only on inventory rows.  Its absence while
    # scheduled must not be interpreted as clearing the target date.
    if (
        old.location == new.location == "todo"
        and old.target_date != new.target_date
    ):
        changes.append(
            _change(
                "target_date_changed",
                "todo",
                new.task_id,
                new.title,
                before=old.target_date,
                after=new.target_date,
            )
        )
    if old.notes is not None and new.notes is not None and old.notes != new.notes:
        changes.append(_change("notes_changed", _task_entity(new), new.task_id, new.title))
    return changes


def _diff_errand(
    old: _ErrandState | None, new: _ErrandState | None
) -> list[dict[str, Any]]:
    if old is None and new is not None:
        return [
            _change(
                "errand_added",
                "errand",
                new.errand_id,
                new.title,
                date=new.date,
            )
        ]
    if old is not None and new is None:
        return [
            _change(
                "deleted",
                "errand",
                old.errand_id,
                old.title,
                date=old.date,
            )
        ]
    if old is None or new is None:  # pragma: no cover - narrowed above
        return []

    changes: list[dict[str, Any]] = []
    if old.status != new.status:
        if old.status == "open" and new.status == "completed":
            changes.append(
                _change(
                    "completed",
                    "errand",
                    new.errand_id,
                    new.title,
                    date=new.date,
                )
            )
        elif old.status == "completed" and new.status == "open":
            changes.append(
                _change(
                    "completion_undone",
                    "errand",
                    new.errand_id,
                    new.title,
                    date=new.date,
                )
            )
    if old.title != new.title:
        changes.append(
            _change(
                "renamed",
                "errand",
                new.errand_id,
                new.title,
                before=old.title,
                after=new.title,
            )
        )
    if (old.start_clock, old.end_clock) != (new.start_clock, new.end_clock):
        changes.append(
            _change(
                "clock_changed",
                "errand",
                new.errand_id,
                new.title,
                before={
                    "startClock": old.start_clock,
                    "endClock": old.end_clock,
                },
                after={
                    "startClock": new.start_clock,
                    "endClock": new.end_clock,
                },
            )
        )
    if old.notes is not None and new.notes is not None and old.notes != new.notes:
        changes.append(_change("notes_changed", "errand", new.errand_id, new.title))
    return changes


def _orders(context: Context) -> dict[tuple[str, str], tuple[bool, list[str]]]:
    days = [dict(context, date=context.get("today")), *_rows(context, "daysAhead")]
    result = {}
    for day in days:
        date = _optional_text(day.get("date"))
        if date is None:
            continue
        for rows, key, field in (("todos", "taskId", "manualTodoOrder"), ("errands", "id", "manualErrandOrder")):
            if field in day:
                result[(date, rows)] = (bool(day[field]), [_required_id(row, key) for row in _rows(day, rows)])
    return result


def _diff_orders(before: Context, after: Context) -> list[dict[str, Any]]:
    old_orders, new_orders = _orders(before), _orders(after)
    changes = []
    for date, kind in sorted(old_orders.keys() & new_orders.keys()):
        old_manual, old_ids = old_orders[(date, kind)]
        new_manual, new_ids = new_orders[(date, kind)]
        shared = set(old_ids) & set(new_ids)
        # Adding/removing rows and automatic clock sorting are not manual reorders.
        changed = new_manual and [i for i in old_ids if i in shared] != [i for i in new_ids if i in shared]
        if old_manual != new_manual or changed:
            changes.append(_change(
                "order_changed", "plan-list" if kind == "todos" else "errand-list", f"{date}:{kind}",
                f"{date} 的{'计划' if kind == 'todos' else '零碎事项'}", date=date,
                before={"manual": old_manual, "ids": old_ids}, after={"manual": new_manual, "ids": new_ids},
            ))
    return changes


def _is_schedule_move(
    old: _TaskState,
    new: _TaskState,
    before_today: str | None,
    after_today: str | None,
) -> bool:
    old_scheduled = old.location in ("plan", "scheduled")
    new_scheduled = new.location in ("plan", "scheduled")
    if not old_scheduled or not new_scheduled:
        return False
    if old.date != new.date:
        return True
    # A day boundary can change the context bucket without an actual reschedule.
    return old.location != new.location and before_today == after_today


def _task_entity(state: _TaskState) -> str:
    return "todo" if state.location == "todo" else "plan"


def _change(
    change_type: str,
    entity: str,
    entity_id: str,
    title: str,
    **details: Any,
) -> dict[str, Any]:
    return {
        "type": change_type,
        "entity": entity,
        "id": entity_id,
        "title": title,
        **details,
    }


def _summarize(counts: Counter[str]) -> str:
    if not counts:
        return "没有发现计划改动"
    parts = [
        f"{_SUMMARY_LABELS[change_type]} {counts[change_type]} 项"
        for change_type in _TYPE_ORDER
        if counts[change_type]
    ]
    return "；".join(parts)


def _rows(context: Context, key: str) -> list[Mapping[str, Any]]:
    value = context.get(key, [])
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _required_id(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None:
        raise ValueError(f"context row missing {key}")
    return str(value)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)
