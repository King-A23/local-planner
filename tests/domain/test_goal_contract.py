"""Independent contract tests for goal revisions, phases, and idempotent writes."""

from __future__ import annotations

import pytest

from local_planner.clock import FrozenClock
from local_planner.domain.commands import add_to_inventory, complete_inventory_task, schedule_to_date
from local_planner.domain.errors import Conflict
from local_planner.domain.goals import change_goal, create_goal
from local_planner.domain.store import InMemoryUnitOfWork


CLOCK = FrozenClock("2026-08-30T12:00:00+08:00")


def _goal(uow: InMemoryUnitOfWork):
    return create_goal(
        CLOCK,
        uow,
        "通过 CSP",
        notes="按阶段练习",
        horizon_text="明年",
        request_id="goal-create-1",
    )


def test_create_and_create_actions_are_idempotent_without_overriding_newer_revision() -> None:
    uow = InMemoryUnitOfWork()
    goal = _goal(uow)
    assert _goal(uow) == goal

    phase_goal = change_goal(
        CLOCK,
        uow,
        goal.id,
        "add-phase",
        expected_revision=goal.revision,
        title="基础",
        notes="两套模拟题",
        request_id="phase-create-1",
    )
    assert phase_goal.revision == 2
    assert len(uow.list_phases(goal.id)) == 1
    assert change_goal(
        CLOCK,
        uow,
        goal.id,
        "add-phase",
        expected_revision=goal.revision,
        title="基础",
        notes="两套模拟题",
        request_id="phase-create-1",
    ) == phase_goal
    assert len(uow.list_phases(goal.id)) == 1

    with pytest.raises(Conflict, match="不同操作"):
        change_goal(
            CLOCK,
            uow,
            goal.id,
            "add-phase",
            expected_revision=phase_goal.revision,
            title="冲突",
            notes="",
            request_id="phase-create-1",
        )


def test_phase_finish_clears_focus_and_next_but_never_completes_the_task() -> None:
    uow = InMemoryUnitOfWork()
    goal = _goal(uow)
    goal = change_goal(
        CLOCK, uow, goal.id, "add-phase", expected_revision=goal.revision,
        title="基础", notes="", request_id="phase-create-1",
    )
    phase = uow.list_phases(goal.id)[0]
    goal = change_goal(
        CLOCK, uow, goal.id, "add-task", expected_revision=goal.revision,
        title="做模拟题", notes="记录错题", phase_id=phase.id, request_id="task-create-1",
    )
    task = uow.list_goal_tasks(goal.id)[0]
    goal = change_goal(
        CLOCK, uow, goal.id, "next", expected_revision=goal.revision, task_id=task.id,
    )
    goal = change_goal(
        CLOCK, uow, goal.id, "focus-phase", expected_revision=goal.revision, phase_id=phase.id,
    )
    goal = change_goal(
        CLOCK, uow, goal.id, "edit-phase", expected_revision=goal.revision,
        phase_id=phase.id, title="基础", notes="", status="done",
    )

    assert goal.next_task_id is None
    assert goal.focus_phase_id is None
    assert uow.get_task(task.id).completed_at is None
    assert uow.get_phase(phase.id).status == "done"


def test_stale_revision_and_paused_schedule_fail_without_changes() -> None:
    uow = InMemoryUnitOfWork()
    goal = _goal(uow)
    with pytest.raises(Conflict, match="发生变化"):
        change_goal(
            CLOCK, uow, goal.id, "edit", expected_revision=0,
            title="不会写入", notes="", horizon_text="",
        )
    assert uow.get_goal(goal.id).title == "通过 CSP"

    goal = change_goal(
        CLOCK, uow, goal.id, "add-task", expected_revision=goal.revision,
        title="做模拟题", notes="", phase_id=None, request_id="task-create-1",
    )
    task = uow.list_goal_tasks(goal.id)[0]
    goal = change_goal(
        CLOCK, uow, goal.id, "next", expected_revision=goal.revision, task_id=task.id,
    )
    goal = change_goal(
        CLOCK, uow, goal.id, "state", expected_revision=goal.revision,
        state="paused", end_reason=None,
    )
    with pytest.raises(Conflict, match="恢复目标"):
        change_goal(
            CLOCK, uow, goal.id, "schedule-next", expected_revision=goal.revision,
            expected_task_id=task.id, expected_scheduled_date=None,
        )
    assert uow.get_task(task.id).current_scheduled_date is None


def test_scheduling_a_goal_task_captures_goal_and_phase_context_on_today() -> None:
    uow = InMemoryUnitOfWork()
    goal = _goal(uow)
    goal = change_goal(
        CLOCK, uow, goal.id, "add-phase", expected_revision=goal.revision,
        title="基础", notes="", request_id="phase-create-1",
    )
    phase = uow.list_phases(goal.id)[0]
    goal = change_goal(
        CLOCK, uow, goal.id, "add-task", expected_revision=goal.revision,
        title="做模拟题", notes="", phase_id=phase.id, request_id="task-create-1",
    )
    task = uow.list_goal_tasks(goal.id)[0]

    schedule_to_date(CLOCK, uow, task.id, CLOCK.today())
    entry = uow.get_entry(CLOCK.today(), task.id)
    assert entry.goal_id_snapshot == goal.id
    assert entry.goal_title_snapshot == "通过 CSP"
    assert entry.phase_id_snapshot == phase.id
    assert entry.phase_title_snapshot == "基础"


def test_roadmap_actions_materialize_once_and_can_be_scheduled_today() -> None:
    uow = InMemoryUnitOfWork()
    goal = _goal(uow)
    goal = change_goal(
        CLOCK, uow, goal.id, "add-action", expected_revision=goal.revision,
        title="完成一套模拟题", notes="记录错题", phase_id=None, request_id="action-1",
    )
    action = uow.list_goal_actions(goal.id)[0]
    goal = change_goal(
        CLOCK, uow, goal.id, "next-action", expected_revision=goal.revision, action_id=action.id,
    )
    scheduled = change_goal(
        CLOCK, uow, goal.id, "materialize-action", expected_revision=goal.revision,
        action_id=action.id, destination="today", request_id="materialize-1",
    )
    linked = uow.get_goal_action(action.id)
    assert linked.task_id is not None
    assert uow.get_task(linked.task_id).current_scheduled_date == CLOCK.today()
    assert scheduled.next_action_id is None
    assert scheduled.next_task_id == linked.task_id

    # A lost response retries without creating a second Task or touching revision.
    assert change_goal(
        CLOCK, uow, goal.id, "materialize-action", expected_revision=goal.revision,
        action_id=action.id, destination="today", request_id="materialize-1",
    ) == scheduled
    assert len(uow.list_goal_tasks(goal.id)) == 1

    # Selecting a materialized roadmap row is still the ordinary task next step.
    selected = change_goal(
        CLOCK, uow, goal.id, "next-action", expected_revision=scheduled.revision,
        action_id=action.id,
    )
    assert selected.next_action_id is None
    assert selected.next_task_id == linked.task_id


def test_goal_parent_rejects_cycles() -> None:
    uow = InMemoryUnitOfWork()
    parent = _goal(uow)
    child = create_goal(CLOCK, uow, "准备算法", request_id="child")
    child = change_goal(CLOCK, uow, child.id, "set-parent", expected_revision=child.revision, parent_goal_id=parent.id)
    assert child.parent_goal_id == parent.id
    with pytest.raises(Exception, match="循环"):
        change_goal(CLOCK, uow, parent.id, "set-parent", expected_revision=parent.revision, parent_goal_id=child.id)


def test_linking_a_completed_task_clears_selected_candidate_instead_of_selecting_it() -> None:
    uow = InMemoryUnitOfWork()
    goal = _goal(uow)
    goal = change_goal(
        CLOCK, uow, goal.id, "add-action", expected_revision=goal.revision,
        title="复盘模拟题", notes="", phase_id=None, request_id="candidate",
    )
    action = uow.list_goal_actions(goal.id)[0]
    goal = change_goal(
        CLOCK, uow, goal.id, "next-action", expected_revision=goal.revision, action_id=action.id,
    )
    task = add_to_inventory(CLOCK, uow, "已完成的复盘").task
    complete_inventory_task(CLOCK, uow, task.id)
    linked = change_goal(
        CLOCK, uow, goal.id, "link-action", expected_revision=goal.revision,
        action_id=action.id, task_id=task.id, expected_task_id=task.id,
    )
    assert linked.next_action_id is None
    assert linked.next_task_id is None
