from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from local_planner.clock import FrozenClock
from local_planner.domain import commands as cmds
from local_planner.domain.errors import Conflict, NotFound
from local_planner.domain.settlement import ensure_settled
from local_planner.domain.store import InMemoryUnitOfWork, UnitOfWork
from local_planner.persistence import SqliteUnitOfWork


@pytest.fixture(params=["memory", "sqlite"])
def uow(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[UnitOfWork]:
    if request.param == "memory":
        yield InMemoryUnitOfWork()
        return
    store = SqliteUnitOfWork.open(tmp_path / "planner.sqlite")
    try:
        yield store
    finally:
        store.close()


def test_offline_days_materialize_before_settlement(uow: UnitOfWork) -> None:
    clock = FrozenClock("2026-08-30T08:00:00+08:00")
    with uow.transaction():
        ensure_settled(clock, uow)
        cmds.create_recurrence(
            clock,
            uow,
            kind="plan",
            title="每日复盘",
            frequency="daily",
            weekdays=None,
            start_date="2026-08-30",
        )
        cmds.create_recurrence(
            clock,
            uow,
            kind="errand",
            title="吃药",
            frequency="daily",
            weekdays=None,
            start_date="2026-08-30",
        )

    clock.set("2026-09-01T08:00:00+08:00")
    with uow.transaction():
        ensure_settled(clock, uow)

    inventory = cmds.list_inventory(uow)
    assert [item.task.occurrence_date for item in inventory] == [
        "2026-08-31",
        "2026-08-30",
    ]
    assert cmds.open_day(clock, uow, "2026-08-30").errands[0].status == "expired"
    assert cmds.open_day(clock, uow, "2026-08-31").errands[0].status == "expired"
    today = cmds.open_day(clock, uow, "2026-09-01")
    assert len(today.todos) == 1
    assert len(today.errands) == 1


def test_future_open_is_idempotent_and_generated_instance_is_independent(
    uow: UnitOfWork,
) -> None:
    clock = FrozenClock("2026-08-30T08:00:00+08:00")
    with uow.transaction():
        ensure_settled(clock, uow)
        series = cmds.create_recurrence(
            clock,
            uow,
            kind="plan",
            title="旧标题",
            frequency="daily",
            weekdays=None,
            start_date="2026-08-31",
        )
        first = cmds.open_day(clock, uow, "2026-09-02")
        second = cmds.open_day(clock, uow, "2026-09-02")
        assert len(first.todos) == len(second.todos) == 1
        cmds.update_recurrence(clock, uow, series.id, title="新标题")
        assert cmds.open_day(clock, uow, "2026-09-02").todos[0].title_snapshot == "旧标题"
        assert cmds.open_day(clock, uow, "2026-09-03").todos[0].title_snapshot == "新标题"


def test_pause_resume_and_stop_only_affect_ungenerated_occurrences(
    uow: UnitOfWork,
) -> None:
    clock = FrozenClock("2026-08-30T08:00:00+08:00")
    with uow.transaction():
        ensure_settled(clock, uow)
        series = cmds.create_recurrence(
            clock,
            uow,
            kind="errand",
            title="吃药",
            frequency="daily",
            weekdays=None,
            start_date="2026-08-30",
        )
        cmds.pause_recurrence(clock, uow, series.id)
        assert cmds.open_day(clock, uow, "2026-08-31").errands == []
    clock.set("2026-08-31T08:00:00+08:00")
    with uow.transaction():
        ensure_settled(clock, uow)
        cmds.resume_recurrence(clock, uow, series.id)
        assert len(cmds.open_day(clock, uow, "2026-08-31").errands) == 1
        cmds.stop_recurrence(clock, uow, series.id)
        assert cmds.open_day(clock, uow, "2026-09-01").errands == []


def test_only_stopped_recurrence_can_be_deleted_and_history_keeps_source(
    uow: UnitOfWork,
) -> None:
    clock = FrozenClock("2026-08-30T08:00:00+08:00")
    with uow.transaction():
        ensure_settled(clock, uow)
        series = cmds.create_recurrence(
            clock,
            uow,
            kind="plan",
            title="每日复盘",
            frequency="daily",
            weekdays=None,
            start_date="2026-08-30",
        )
        occurrence = cmds.open_day(clock, uow, "2026-08-30").todos[0]
        with pytest.raises(Conflict, match="只有已停止"):
            cmds.delete_recurrence(clock, uow, series.id)
        cmds.pause_recurrence(clock, uow, series.id)
        with pytest.raises(Conflict, match="只有已停止"):
            cmds.delete_recurrence(clock, uow, series.id)
        cmds.stop_recurrence(clock, uow, series.id)
        cmds.delete_recurrence(clock, uow, series.id)

        assert cmds.list_recurrences(uow) == []
        tombstone = uow.get_recurrence(series.id)
        assert tombstone is not None
        assert tombstone.deleted_at is not None
        assert uow.get_occurrence(series.id, "2026-08-30") is not None
        retained = cmds.open_day(clock, uow, "2026-08-30").todos[0]
        assert retained.task_id == occurrence.task_id
        assert retained.series_id == series.id
        with pytest.raises(NotFound):
            cmds.stop_recurrence(clock, uow, series.id)


def test_deleted_only_series_is_not_planning_relevant_but_remains_persistent(
    uow: UnitOfWork,
) -> None:
    clock = FrozenClock("2026-08-30T08:00:00+08:00")
    with uow.transaction():
        series = cmds.create_recurrence(
            clock,
            uow,
            kind="errand",
            title="未来事项",
            frequency="daily",
            weekdays=None,
            start_date="2026-09-01",
        )
        cmds.stop_recurrence(clock, uow, series.id)
        cmds.delete_recurrence(clock, uow, series.id)
        assert uow.earliest_relevant_date() is None
        # A tombstone is retained data/provenance, so the store is not physically empty.
        assert not uow.is_proven_empty()


def test_planning_candidates_status_and_upcoming_projection(uow: UnitOfWork) -> None:
    clock = FrozenClock("2026-08-30T08:00:00+08:00")
    with uow.transaction():
        ensure_settled(clock, uow)
        due = cmds.add_to_inventory(clock, uow, "到期项", "2026-08-30")
        yesterday = cmds.add_todo_on_day(clock, uow, "2026-08-30", "昨日项")
        cmds.set_target_date(
            clock, uow, yesterday.todos[0].task_id, "2026-08-30"
        )
        cmds.create_recurrence(
            clock,
            uow,
            kind="plan",
            title="未来定期",
            frequency="daily",
            weekdays=None,
            start_date="2026-09-01",
        )
    clock.set("2026-08-31T08:00:00+08:00")
    with uow.transaction():
        ensure_settled(clock, uow)
        view = cmds.open_planning_today(clock, uow)
        assert view.status == "unplanned"
        assert {item.task.id for item in view.returned_from_yesterday} == {
            yesterday.todos[0].task_id
        }
        assert {item.task.id for item in view.due} == {due.task.id}
        assert view.inventory == []
        assert view.upcoming[0].date == "2026-09-01"
        assert view.upcoming[0].todo_count == 0
        assert view.upcoming[0].recurrence_count == 1
        ready = cmds.complete_planning_today(clock, uow)
        assert ready.status == "ready"
        assert ready.planned_at is not None
