"""Transport for durable planning drafts, using the existing planner transaction."""
from typing import Any, Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, Field

from local_planner.domain import planning


class DraftCreateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goalId: str | None = None
    selectedPhaseId: str | None = None
    requestId: str = Field(min_length=1, max_length=100)
    recoveryGeneration: str | None


class DraftActionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["update", "undo", "apply", "discard", "revert"]
    expectedRevision: int = Field(ge=1)
    recoveryGeneration: str | None
    requestId: str = Field(min_length=1, max_length=100)
    document: dict[str, Any] | None = None


def mount_planning(app: FastAPI, ctx, locked):
    def response(data, today):
        return {**data, "serverToday": today}

    @app.get("/api/planning/drafts")
    def list_drafts(goalId: str | None = None):
        return locked(ctx, lambda today: {"items": planning.list_drafts(ctx.uow, goalId),
                                         "serverToday": today, "recoveryGeneration": ctx.uow.meta.get("recovery_generation")})

    @app.post("/api/planning/drafts")
    def create_draft(body: DraftCreateBody):
        return locked(ctx, lambda today: response(planning.create_draft(
            ctx.clock, ctx.uow, goal_id=body.goalId, phase_id=body.selectedPhaseId,
            request_id=body.requestId, recovery_generation=body.recoveryGeneration), today))

    @app.get("/api/planning/drafts/{draft_id}")
    def get_draft(draft_id: str):
        return locked(ctx, lambda today: response(planning.get_draft(ctx.uow, draft_id), today))

    @app.post("/api/planning/drafts/{draft_id}/actions")
    def change_draft(draft_id: str, body: DraftActionBody):
        return locked(ctx, lambda today: response(planning.change_draft(
            ctx.clock, ctx.uow, draft_id, body.operation, expected_revision=body.expectedRevision,
            recovery_generation=body.recoveryGeneration, request_id=body.requestId, document=body.document), today))
