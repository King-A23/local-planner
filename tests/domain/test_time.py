from __future__ import annotations

import pytest

from local_planner.clock import FrozenClock
from local_planner.domain.commands import Planner
from local_planner.domain.errors import ValidationError
from local_planner.domain.settlement import ensure_settled
from local_planner.domain.time import parse_clock, validate_clock_pair
from local_planner.persistence import SqliteUnitOfWork

TODAY = "2026-08-31"
YESTERDAY = "2026-08-30"
FROZEN = "2026-08-31T08:00:00+08:00"


def test_parse_clock_grid_and_pair():
    assert parse_clock("9") == "09:00"
    assert parse_clock("21:30") == "21:30"
    assert parse_clock("") is None
    assert parse_clock(None) is None
    with pytest.raises(ValidationError):
        parse_clock("9:03")
    with pytest.raises(ValidationError):
        parse_clock("24:00")
    with pytest.raises(ValidationError):
        validate_clock_pair("10:00", "09:00")
    assert validate_clock_pair("09:00", None) == ("09:00", None)
    assert validate_clock_pair(None, "17:00") == (None, "17:00")
    assert validate_clock_pair("09:00", "09:00") == ("09:00", "09:00")


def test_todo_target_date_stays_unscheduled(tmp_path):
    clock = FrozenClock(FROZEN)
    uow = SqliteUnitOfWork.open(tmp_path / "planner.sqlite")
    planner = Planner(clock, uow)
    with uow.transaction():
        item = planner.add_to_inventory("目标日任务", "2026-09-03")
        assert item.task.current_scheduled_date is None
        assert item.task.target_date == "2026-09-03"
        today = planner.open_day(TODAY)
        assert today.todos == []
        listed = planner.list_inventory()
        assert listed[0].task.target_date == "2026-09-03"
        assert listed[0].task.id == item.task.id
        planner.schedule_to_date(item.task.id, TODAY)
        back = planner.unschedule(item.task.id)
        assert back.task.target_date == "2026-09-03"
        assert back.task.current_scheduled_date is None
        assert planner.open_day(TODAY).todos == []
    uow.close()


def test_plan_and_errand_clocks_optional_and_not_carried_on_settle(tmp_path):
    clock = FrozenClock(FROZEN)
    uow = SqliteUnitOfWork.open(tmp_path / "planner.sqlite")
    planner = Planner(clock, uow)
    with uow.transaction():
        start_only = planner.add_todo_on_day(TODAY, "只开始", "09:00", None)
        end_only = planner.add_todo_on_day(TODAY, "只结束", None, "17:00")
        both = planner.add_todo_on_day(TODAY, "两端", "09:00", "11:00")
        neither = planner.add_todo_on_day(TODAY, "不填")
        by_title = {e.title_snapshot: e for e in neither.todos}
        assert by_title["只开始"].start_clock == "09:00"
        assert by_title["只开始"].end_clock is None
        assert by_title["只结束"].start_clock is None
        assert by_title["只结束"].end_clock == "17:00"
        assert by_title["两端"].start_clock == "09:00"
        assert by_title["两端"].end_clock == "11:00"
        assert by_title["不填"].start_clock is None
        assert by_title["不填"].end_clock is None
        errands = planner.add_errand(TODAY, "差事钟", "13:00", "14:00")
        assert errands.errands[0].start_clock == "13:00"
        assert errands.errands[0].end_clock == "14:00"

    clock.set("2026-09-01T00:05:00+08:00")
    with uow.transaction():
        ensure_settled(clock, uow)
        inv = {item.task.title: item.task for item in planner.list_inventory()}
        assert "只开始" in inv
        assert inv["只开始"].target_date is None
        yesterday = planner.open_day(TODAY)
        hist = {e.title_snapshot: e for e in yesterday.todos}
        assert hist["只开始"].start_clock == "09:00"
        assert hist["两端"].end_clock == "11:00"
        assert yesterday.errands[0].start_clock == "13:00"
        fresh = planner.open_day("2026-09-01")
        assert fresh.todos == []
    uow.close()
