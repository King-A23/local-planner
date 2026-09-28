"""Longer-term goals and optional flat phases; caller owns the transaction.

Actions reuse ordinary Tasks. A goal never owns scheduling or completion rules.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import replace
from typing import Any

from local_planner.clock import Clock, format_utc
from local_planner.domain.errors import Conflict, NotFound, ValidationError
from local_planner.domain.models import Goal, GoalPhase, Task, normalize_notes, normalize_title
from local_planner.domain.store import UnitOfWork


def _now(clock: Clock) -> str:
    return format_utc(clock.now_utc())


def require_goal(uow: UnitOfWork, goal_id: str) -> Goal:
    goal = uow.get_goal(goal_id)
    if goal is None:
        raise NotFound("找不到该目标")
    return goal


def _phase(uow: UnitOfWork, goal: Goal, phase_id: str, *, open_only: bool = False) -> GoalPhase:
    phase = uow.get_phase(phase_id)
    if phase is None or phase.goal_id != goal.id:
        raise ValidationError("阶段不属于这个目标")
    if open_only and phase.status != "open":
        raise Conflict("请先重新打开这个阶段")
    return phase


def _task(uow: UnitOfWork, task_id: str, *, unfinished: bool = True) -> Task:
    task = uow.get_task(task_id)
    if task is None or task.discarded_at is not None:
        raise NotFound("找不到该事项")
    if unfinished and task.completed_at is not None:
        raise Conflict("事项已完成，请选择未完成事项")
    return task


def _horizon(value: str) -> str:
    if not isinstance(value, str) or len(value) > 200:
        raise ValidationError("大致时间最长 200 字")
    return value.strip()


def _request(uow: UnitOfWork, request_id: str, values: dict) -> tuple[str, Goal | None]:
    if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 100:
        raise ValidationError("需要有效的 requestId（1–100 字）")
    fingerprint = hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    prior = uow.get_goal_request(request_id)
    if prior:
        if prior[0] != fingerprint:
            raise Conflict("同一 requestId 已用于不同操作，请核对后重试")
        return fingerprint, require_goal(uow, prior[1])
    return fingerprint, None


def _save_changed(clock: Clock, uow: UnitOfWork, goal: Goal, **values: Any) -> Goal:
    updated = replace(goal, revision=goal.revision + 1, updated_at=_now(clock), **values)
    uow.save_goal(updated)
    return updated


def create_goal(clock: Clock, uow: UnitOfWork, title: str, *, notes: str = "",
                horizon_text: str = "", request_id: str) -> Goal:
    title, notes, horizon_text = normalize_title(title), normalize_notes(notes), _horizon(horizon_text)
    fingerprint, prior = _request(uow, request_id, dict(operation="create", title=title, notes=notes, horizon_text=horizon_text))
    if prior:
        return prior
    goal = Goal(str(uuid.uuid4()), title, notes, horizon_text, "active", None, None, None, 1, _now(clock), _now(clock))
    uow.save_goal(goal)
    uow.save_goal_request(request_id, fingerprint, goal.id)
    return goal


def snapshot_fields(uow: UnitOfWork, task: Task) -> dict[str, str | None]:
    goal = uow.get_goal(task.goal_id) if task.goal_id else None
    phase = uow.get_phase(task.phase_id) if task.phase_id else None
    return dict(goal_id_snapshot=goal.id if goal else None,
                goal_title_snapshot=goal.title if goal else None,
                phase_id_snapshot=phase.id if phase else None,
                phase_title_snapshot=phase.title if phase else None)


def refresh_task_snapshots(clock: Clock, uow: UnitOfWork, task: Task) -> None:
    from local_planner.domain.commands import is_day_writable
    fields = snapshot_fields(uow, task)
    for entry in uow.list_entries_for_task(task.id):
        if is_day_writable(clock, uow, entry.day_date):
            uow.save_entry(replace(entry, **fields))


def touch_goal(clock: Clock, uow: UnitOfWork, goal: Goal) -> Goal:
    """Record a membership change without replacing the current next-step selection."""
    return _save_changed(clock, uow, goal)


def task_changed(clock: Clock, uow: UnitOfWork, before: Task, after: Task | None) -> None:
    """Called by existing task commands, including hard deletion before its SQL DELETE."""
    if before.goal_id is None or before == after:
        return
    goal = uow.get_goal(before.goal_id)
    if goal is None:
        return
    invalid = after is None or after.completed_at is not None or after.discarded_at is not None or after.goal_id != goal.id
    _save_changed(clock, uow, goal, next_task_id=None if invalid and goal.next_task_id == before.id else goal.next_task_id)


def change_goal(clock: Clock, uow: UnitOfWork, goal_id: str, operation: str, *, expected_revision: int, **values: Any) -> Goal:
    from local_planner.domain import commands

    goal = require_goal(uow, goal_id)
    allowed = {
        "edit": {"title", "notes", "horizon_text"},
        "state": {"state", "end_reason"},
        "add-task": {"title", "notes", "phase_id", "request_id"},
        "link-task": {"task_id", "phase_id", "expected_goal_id"},
        "unlink-task": {"task_id"}, "next": {"task_id"},
        "schedule-next": {"expected_task_id", "expected_scheduled_date"},
        "add-phase": {"title", "notes", "request_id"},
        "edit-phase": {"phase_id", "title", "notes", "status"},
        "focus-phase": {"phase_id"}, "reorder-phases": {"phase_ids"},
    }
    if operation not in allowed or set(values) - allowed[operation]:
        raise ValidationError("目标操作或参数无效")
    # Retry lookup precedes revision validation: lost responses must never create duplicates.
    request_id = values.get("request_id")
    fingerprint = None
    if operation in {"add-task", "add-phase"}:
        fingerprint, prior = _request(uow, request_id, dict(operation=operation, goal_id=goal_id, **values))
        if prior:
            return prior
    if type(expected_revision) is not int or expected_revision != goal.revision:
        raise Conflict("目标已发生变化，请刷新后重试，当前草稿仍可保留")
    if goal.state == "ended" and operation not in {"edit", "state"}:
        raise Conflict("目标已结束，请先恢复目标")

    updates: dict[str, Any] = {}
    if operation == "edit":
        updates = dict(title=normalize_title(values.get("title")), notes=normalize_notes(values.get("notes")), horizon_text=_horizon(values.get("horizon_text")))
    elif operation == "state":
        state, reason = values.get("state"), values.get("end_reason")
        if state not in {"active", "paused", "ended"} or (state == "ended" and reason not in {"achieved", "abandoned"}) or (state != "ended" and reason is not None):
            raise ValidationError("目标状态或结束原因无效")
        updates = dict(state=state, end_reason=reason, ended_at=_now(clock) if state == "ended" else None)
    elif operation in {"add-task", "link-task"}:
        phase_id = values.get("phase_id")
        if phase_id is not None:
            _phase(uow, goal, phase_id, open_only=True)
        if operation == "add-task":
            title, notes = normalize_title(values.get("title")), normalize_notes(values.get("notes", ""))
            task = commands.add_to_inventory(clock, uow, title).task
            task = replace(task, notes=notes)
        else:
            task = _task(uow, values.get("task_id"))
            if "expected_goal_id" not in values or task.goal_id != values["expected_goal_id"]:
                raise Conflict("事项的目标关联已变化，请刷新后重试")
            if task.goal_id not in {None, goal.id}:
                raise Conflict("事项已属于其他目标，请先解除原关联")
            if task.current_scheduled_date:
                commands.require_writable_day(clock, uow, task.current_scheduled_date)
        task = replace(task, goal_id=goal.id, phase_id=phase_id)
        uow.save_task(task)
        refresh_task_snapshots(clock, uow, task)
    elif operation == "unlink-task":
        task = _task(uow, values.get("task_id"), unfinished=False)
        if task.goal_id != goal.id:
            raise Conflict("事项不属于这个目标")
        if task.current_scheduled_date:
            commands.require_writable_day(clock, uow, task.current_scheduled_date)
        uow.save_task(replace(task, goal_id=None, phase_id=None))
        refresh_task_snapshots(clock, uow, replace(task, goal_id=None, phase_id=None))
        if goal.next_task_id == task.id:
            updates["next_task_id"] = None
    elif operation == "next":
        if "task_id" not in values:
            raise ValidationError("需要 taskId，清空时传 null")
        task_id = values["task_id"]
        if task_id is not None:
            task = _task(uow, task_id)
            if task.goal_id != goal.id:
                raise Conflict("请选择这个目标中的事项")
            if task.phase_id:
                _phase(uow, goal, task.phase_id, open_only=True)
        updates["next_task_id"] = task_id
    elif operation == "schedule-next":
        if goal.state != "active":
            raise Conflict("请先恢复目标，再安排下一步")
        if not goal.next_task_id or values.get("expected_task_id") != goal.next_task_id:
            raise Conflict("下一步已变化，请刷新后重试")
        task = _task(uow, goal.next_task_id)
        if task.goal_id != goal.id:
            raise Conflict("下一步已不属于这个目标")
        if "expected_scheduled_date" not in values or values["expected_scheduled_date"] != task.current_scheduled_date:
            raise Conflict("事项的安排已变化，请刷新后重试")
        commands.schedule_to_date(clock, uow, task.id, clock.today())
        return require_goal(uow, goal.id)
    elif operation == "add-phase":
        phase = GoalPhase(str(uuid.uuid4()), goal.id, normalize_title(values.get("title")), normalize_notes(values.get("notes", "")), len(uow.list_phases(goal.id)))
        uow.save_phase(phase)
    elif operation == "edit-phase":
        phase = _phase(uow, goal, values.get("phase_id"))
        status = values.get("status")
        if status not in {"open", "done", "skipped"}:
            raise ValidationError("阶段状态无效")
        updated = replace(phase, title=normalize_title(values.get("title")), notes=normalize_notes(values.get("notes")), status=status)
        uow.save_phase(updated)
        if status != "open":
            if goal.focus_phase_id == phase.id:
                updates["focus_phase_id"] = None
            task = uow.get_task(goal.next_task_id) if goal.next_task_id else None
            if task and task.phase_id == phase.id:
                updates["next_task_id"] = None
    elif operation == "focus-phase":
        if "phase_id" not in values:
            raise ValidationError("需要 phaseId，清空时传 null")
        phase_id = values["phase_id"]
        if phase_id is not None:
            _phase(uow, goal, phase_id, open_only=True)
        updates["focus_phase_id"] = phase_id
    elif operation == "reorder-phases":
        phases = uow.list_phases(goal.id)
        ids = values.get("phase_ids")
        if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids) or set(ids) != {p.id for p in phases}:
            raise Conflict("阶段列表已变化，请刷新后重试")
        for phase in phases:
            uow.save_phase(replace(phase, position=ids.index(phase.id)))

    goal = _save_changed(clock, uow, goal, **updates)
    if operation in {"edit", "edit-phase"}:
        for task in uow.list_goal_tasks(goal.id):
            refresh_task_snapshots(clock, uow, task)
    if fingerprint is not None:
        uow.save_goal_request(request_id, fingerprint, goal.id)
    return goal


def task_payload(task: Task) -> dict[str, Any]:
    return dict(taskId=task.id, title=task.title, notes=task.notes, goalId=task.goal_id,
                phaseId=task.phase_id, scheduledDate=task.current_scheduled_date,
                completed=task.completed_at is not None, targetDate=task.target_date, seriesId=task.series_id)


def goal_payload(uow: UnitOfWork, goal: Goal) -> dict[str, Any]:
    return dict(id=goal.id, title=goal.title, notes=goal.notes, horizonText=goal.horizon_text,
                state=goal.state, endReason=goal.end_reason, nextTaskId=goal.next_task_id,
                focusPhaseId=goal.focus_phase_id, revision=goal.revision,
                createdAt=goal.created_at, updatedAt=goal.updated_at, endedAt=goal.ended_at,
                phases=[dict(id=p.id, goalId=p.goal_id, title=p.title, notes=p.notes, position=p.position, status=p.status) for p in uow.list_phases(goal.id)],
                tasks=[task_payload(t) for t in uow.list_goal_tasks(goal.id)])


def list_goal_payloads(uow: UnitOfWork) -> list[dict[str, Any]]:
    return [goal_payload(uow, g) for g in uow.list_goals()]


def goal_candidates(clock: Clock, uow: UnitOfWork) -> list[dict[str, Any]]:
    tasks = {t.id: t for t in uow.list_inventory_tasks() + uow.list_scheduled_after(clock.today())}
    for entry in uow.list_entries(clock.today()):
        task = uow.get_task(entry.task_id)
        if task and task.completed_at is None and task.discarded_at is None:
            tasks[task.id] = task
    rows = []
    for task in tasks.values():
        goal = uow.get_goal(task.goal_id) if task.goal_id else None
        rows.append(dict(**task_payload(task), goalTitle=goal.title if goal else None))
    return rows
