"""HTTP adapters for long-term goals.

The routes deliberately contain only JSON naming, generation checks, and request
shape checks.  Goal lifecycle and task linking remain in ``domain.goals``.
"""

from __future__ import annotations

from typing import Any, Callable, Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from local_planner.domain import goals
from local_planner.domain.errors import Conflict, NotFound, ValidationError


class GoalCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    notes: str = ""
    horizonText: str = ""
    requestId: str = Field(min_length=1, max_length=100)
    recoveryGeneration: str | None


class GoalActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal[
        "edit", "state", "add-task", "link-task", "unlink-task", "next",
        "schedule-next", "add-phase", "edit-phase", "focus-phase",
        "reorder-phases", "set-parent", "add-action", "edit-action",
        "remove-action", "next-action", "materialize-action", "link-action",
    ]
    expectedRevision: int = Field(ge=1)
    recoveryGeneration: str | None
    title: str | None = None
    notes: str | None = None
    horizonText: str | None = None
    state: Literal["active", "paused", "ended"] | None = None
    status: Literal["open", "done", "skipped"] | None = None
    endReason: Literal["achieved", "abandoned"] | None = None
    requestId: str | None = Field(default=None, min_length=1, max_length=100)
    taskId: str | None = None
    phaseId: str | None = None
    expectedGoalId: str | None = None
    expectedScheduledDate: str | None = None
    phaseIds: list[str] | None = None
    parentGoalId: str | None = None
    actionId: str | None = None
    outcome: str | None = None
    destination: Literal["today", "inventory"] | None = None
    expectedTaskId: str | None = None


def _generation(ctx: Any) -> str | None:
    return ctx.uow.meta.get("recovery_generation")


def _check_generation(ctx: Any, supplied: str | None) -> None:
    if supplied != _generation(ctx):
        raise Conflict("数据已恢复，请刷新目标后再修改")


def _response(ctx: Any, goal: Any, today: str) -> dict[str, Any]:
    return goals.goal_payload(ctx.uow, goal) | {
        "serverToday": today,
        "recoveryGeneration": _generation(ctx),
    }


def _required_text(body: GoalActionBody, key: str) -> str:
    value = getattr(body, key)
    if key not in body.model_fields_set or not isinstance(value, str):
        raise ValidationError("请求缺少必要字段")
    return value


def _required_nullable(body: GoalActionBody, key: str) -> Any:
    if key not in body.model_fields_set:
        raise ValidationError("请求缺少必要字段")
    return getattr(body, key)


def _only_fields(body: GoalActionBody, *allowed: str) -> None:
    base = {"operation", "expectedRevision", "recoveryGeneration"}
    if body.model_fields_set - base - set(allowed):
        raise ValidationError("目标操作包含不适用字段")


def _action_values(body: GoalActionBody) -> dict[str, Any]:
    operation = body.operation
    if operation == "edit":
        _only_fields(body, "title", "notes", "horizonText")
        return {
            "title": _required_text(body, "title"),
            "notes": _required_text(body, "notes"),
            "horizon_text": _required_text(body, "horizonText"),
        }
    if operation == "state":
        _only_fields(body, "state", "endReason")
        state = _required_text(body, "state")
        if state == "ended" and body.endReason is None:
            raise ValidationError("结束目标时必须说明原因")
        if state != "ended" and body.endReason is not None:
            raise ValidationError("只有结束目标时可以说明结束原因")
        return {"state": state, "end_reason": body.endReason}
    if operation == "set-parent":
        _only_fields(body, "parentGoalId")
        return {"parent_goal_id": _required_nullable(body, "parentGoalId")}
    if operation == "add-task":
        _only_fields(body, "title", "notes", "phaseId", "requestId")
        return {
            "title": _required_text(body, "title"),
            "notes": body.notes or "",
            "phase_id": body.phaseId,
            "request_id": _required_text(body, "requestId"),
        }
    if operation == "link-task":
        _only_fields(body, "taskId", "phaseId", "expectedGoalId")
        return {
            "task_id": _required_text(body, "taskId"),
            "phase_id": body.phaseId,
            "expected_goal_id": _required_nullable(body, "expectedGoalId"),
        }
    if operation == "unlink-task":
        _only_fields(body, "taskId")
        return {"task_id": _required_text(body, "taskId")}
    if operation == "next":
        _only_fields(body, "taskId")
        # null is a meaningful instruction to clear the selected next task.
        return {"task_id": _required_nullable(body, "taskId")}
    if operation == "schedule-next":
        _only_fields(body, "expectedTaskId", "expectedScheduledDate")
        return {
            "expected_task_id": _required_text(body, "expectedTaskId"),
            "expected_scheduled_date": _required_nullable(body, "expectedScheduledDate"),
        }
    if operation == "add-phase":
        _only_fields(body, "title", "notes", "outcome", "horizonText", "requestId")
        result = {
            "title": _required_text(body, "title"),
            "notes": body.notes or "",
            "request_id": _required_text(body, "requestId"),
        }
        if "outcome" in body.model_fields_set:
            result["outcome"] = _required_text(body, "outcome")
        if "horizonText" in body.model_fields_set:
            result["horizon_text"] = _required_text(body, "horizonText")
        return result
    if operation == "edit-phase":
        _only_fields(body, "phaseId", "title", "notes", "status", "outcome", "horizonText")
        result = {
            "phase_id": _required_text(body, "phaseId"),
            "title": _required_text(body, "title"),
            "notes": _required_text(body, "notes"),
            "status": _required_text(body, "status"),
        }
        if "outcome" in body.model_fields_set:
            result["outcome"] = _required_text(body, "outcome")
        if "horizonText" in body.model_fields_set:
            result["horizon_text"] = _required_text(body, "horizonText")
        return result
    if operation == "focus-phase":
        _only_fields(body, "phaseId")
        return {"phase_id": _required_nullable(body, "phaseId")}
    if operation == "reorder-phases":
        _only_fields(body, "phaseIds")
        value = _required_nullable(body, "phaseIds")
        if value is None:
            raise ValidationError("请求缺少必要字段")
        return {"phase_ids": value}
    if operation == "add-action":
        _only_fields(body, "title", "notes", "phaseId", "requestId")
        return {"title": _required_text(body, "title"), "notes": body.notes or "",
                "phase_id": body.phaseId, "request_id": _required_text(body, "requestId")}
    if operation == "edit-action":
        _only_fields(body, "actionId", "title", "notes", "phaseId")
        return {"action_id": _required_text(body, "actionId"), "title": _required_text(body, "title"),
                "notes": _required_text(body, "notes"), "phase_id": _required_nullable(body, "phaseId")}
    if operation == "remove-action":
        _only_fields(body, "actionId")
        return {"action_id": _required_text(body, "actionId")}
    if operation == "next-action":
        _only_fields(body, "actionId")
        return {"action_id": _required_nullable(body, "actionId")}
    if operation == "materialize-action":
        _only_fields(body, "actionId", "destination", "requestId")
        return {"action_id": _required_text(body, "actionId"), "destination": _required_text(body, "destination"),
                "request_id": _required_text(body, "requestId")}
    if operation == "link-action":
        _only_fields(body, "actionId", "taskId", "expectedTaskId")
        return {"action_id": _required_text(body, "actionId"), "task_id": _required_text(body, "taskId"),
                "expected_task_id": _required_nullable(body, "expectedTaskId")}
    raise ValidationError("未知目标操作")


def mount_goals(
    app: FastAPI,
    ctx: Any,
    locked: Callable[[Any, Callable[[str], dict[str, Any]]], dict[str, Any]],
) -> None:
    @app.get("/api/goals")
    def list_goals() -> dict[str, Any]:
        return locked(
            ctx,
            lambda today: {
                "items": goals.list_goal_payloads(ctx.uow),
                "serverToday": today,
                "recoveryGeneration": _generation(ctx),
            },
        )

    @app.get("/api/goals/candidates")
    def list_candidates() -> dict[str, Any]:
        return locked(
            ctx,
            lambda _today: {
                "items": goals.goal_candidates(ctx.clock, ctx.uow)
            },
        )

    @app.get("/api/goals/{goal_id}")
    def get_goal(goal_id: str) -> dict[str, Any]:
        def read(today: str) -> dict[str, Any]:
            goal = ctx.uow.get_goal(goal_id)
            if goal is None:
                raise NotFound("找不到目标")
            return _response(ctx, goal, today)
        return locked(ctx, read)

    @app.post("/api/goals")
    def create_goal(body: GoalCreateBody) -> dict[str, Any]:
        def create(today: str) -> dict[str, Any]:
            _check_generation(ctx, body.recoveryGeneration)
            goal = goals.create_goal(
                ctx.clock,
                ctx.uow,
                body.title,
                notes=body.notes,
                horizon_text=body.horizonText,
                request_id=body.requestId,
            )
            return _response(ctx, goal, today)
        return locked(ctx, create)

    @app.post("/api/goals/{goal_id}/actions")
    def change_goal(goal_id: str, body: GoalActionBody) -> dict[str, Any]:
        def change(today: str) -> dict[str, Any]:
            _check_generation(ctx, body.recoveryGeneration)
            goal = goals.change_goal(
                ctx.clock,
                ctx.uow,
                goal_id,
                body.operation,
                expected_revision=body.expectedRevision,
                **_action_values(body),
            )
            return _response(ctx, goal, today)
        return locked(ctx, change)
