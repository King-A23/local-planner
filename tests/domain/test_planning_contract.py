"""Planning draft invariants that do not depend on HTTP or an agent launcher."""

from __future__ import annotations

import copy

import pytest

from local_planner.clock import FrozenClock
from local_planner.domain import goals, planning
from local_planner.domain.errors import Conflict
from local_planner.domain.store import InMemoryUnitOfWork


CLOCK = FrozenClock("2026-09-29T12:00:00+08:00")


def _goal(uow: InMemoryUnitOfWork, title: str, request_id: str):
    return goals.create_goal(CLOCK, uow, title, request_id=request_id)


def test_in_memory_planning_store_detaches_documents_and_preserves_stable_ids() -> None:
    uow = InMemoryUnitOfWork()
    goal = _goal(uow, "通过 CSP", "goal")
    draft = planning.create_draft(CLOCK, uow, request_id="draft", recovery_generation=None)
    draft["document"]["goals"][0]["title"] = "不能泄漏"
    stored = planning.get_draft(uow, draft["id"])
    assert stored["document"]["goals"][0]["id"] == goal.id
    assert stored["document"]["goals"][0]["title"] == "通过 CSP"


def test_ended_goal_draft_can_edit_text_but_cannot_change_route_or_parent() -> None:
    uow = InMemoryUnitOfWork()
    parent = _goal(uow, "长期方向", "parent")
    ended = _goal(uow, "旧目标", "ended")
    ended = goals.change_goal(
        CLOCK, uow, ended.id, "state", expected_revision=ended.revision,
        state="ended", end_reason="abandoned",
    )
    draft = planning.create_draft(CLOCK, uow, request_id="draft", recovery_generation=None)
    document = copy.deepcopy(draft["document"])
    row = next(item for item in document["goals"] if item["id"] == ended.id)
    row["title"] = "更清楚的旧目标名"
    accepted = planning.normalize_document(uow, planning._raw(uow, draft["id"]), document)
    assert next(item for item in accepted["goals"] if item["id"] == ended.id)["title"] == "更清楚的旧目标名"

    row["parentGoalId"] = parent.id
    with pytest.raises(Conflict, match="已结束"):
        planning.normalize_document(uow, planning._raw(uow, draft["id"]), document)
