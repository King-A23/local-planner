"""Watermark ensure_settled tests. Functions do not BEGIN; tests wrap SQLite."""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from pathlib import Path

import pytest

from local_planner.clock import FrozenClock
from local_planner.domain import settlement as settlement_mod
from local_planner.domain.commands import Planner
from local_planner.domain.errors import DaySealed
from local_planner.domain.models import DayRecord
from local_planner.domain.settlement import (
    day_before,
    ensure_settled,
    inclusive_range,
)
from local_planner.domain.store import InMemoryUnitOfWork, UnitOfWork
from local_planner.persistence import SqliteUnitOfWork

TODAY = "2026-08-30"
YESTERDAY = "2026-08-29"
TOMORROW = "2026-08-31"
SKIP_TO = "2026-09-02"
MIDDLE = "2026-08-31"
FROZEN = "2026-08-30T12:00:00+08:00"


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


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(FROZEN)


@pytest.fixture
def planner(clock: FrozenClock, uow: UnitOfWork) -> Planner:
    return Planner(clock=clock, uow=uow)


def _tid(plan, title: str | None = None) -> str:
    if title is None:
        return plan.todos[0].task_id
    return next(e.task_id for e in plan.todos if e.title_snapshot == title)


def _eid(plan, title: str | None = None) -> str:
    if title is None:
        return plan.errands[0].id
    return next(e.id for e in plan.errands if e.title == title)


def _inv_ids(p: Planner) -> set[str]:
    return {item.task.id for item in p.list_inventory()}


def test_inclusive_range_uses_datetime_date_across_month_and_year() -> None:
    assert inclusive_range("2026-12-31", "2027-01-02") == [
        "2026-12-31",
        "2027-01-01",
        "2027-01-02",
    ]
    assert day_before("2027-01-01") == "2026-12-31"
    source = inspect.getsource(settlement_mod.inclusive_range)
    assert "date.fromisoformat" in source
    assert "timedelta(days=1)" in source


def test_ensure_settled_does_not_lock_or_begin() -> None:
    source = inspect.getsource(settlement_mod)
    assert "BEGIN IMMEDIATE" not in source
    assert "PLANNER_LOCK" not in source
    assert list(inspect.signature(ensure_settled).parameters) == ["clock", "uow"]


def test_unfinished_todo_returns_to_inventory_at_day_boundary(
    planner: Planner, uow: UnitOfWork, clock: FrozenClock
) -> None:
    """5. 日界未勾待办 → 昨天快照未勾；库存出现同一 id；新今天不含。"""
    with uow.transaction():
        ensure_settled(clock, uow)
        plan = planner.add_todo_on_day(TODAY, "未勾待办")
        tid = _tid(plan)
    clock.set("2026-08-31T12:00:00+08:00")
    with uow.transaction():
        ensure_settled(clock, uow)
    yesterday = planner.open_day(TODAY)
    assert yesterday.status == "sealed"
    assert yesterday.todos[0].task_id == tid
    assert yesterday.todos[0].completed_on_day is False
    assert tid in _inv_ids(planner)
    assert planner.get_task(tid).current_scheduled_date is None
    assert all(e.task_id != tid for e in planner.open_day(TOMORROW).todos)


def test_completed_todo_does_not_return_to_inventory(
    planner: Planner, uow: UnitOfWork, clock: FrozenClock
) -> None:
    """6. 日界已勾待办 → 不回库存；昨天已勾。"""
    with uow.transaction():
        ensure_settled(clock, uow)
        plan = planner.add_todo_on_day(TODAY, "已勾待办")
        tid = _tid(plan)
        planner.complete_task_on_day(tid, TODAY)
    clock.set("2026-08-31T12:00:00+08:00")
    with uow.transaction():
        ensure_settled(clock, uow)
    yesterday = planner.open_day(TODAY)
    assert yesterday.status == "sealed"
    assert yesterday.todos[0].completed_on_day is True
    assert tid not in _inv_ids(planner)
    task = planner.get_task(tid)
    assert task.completed_at is not None
    assert task.completed_on_date == TODAY
    assert task.current_scheduled_date is None


def test_open_errand_expires_and_is_not_in_inventory(
    planner: Planner, uow: UnitOfWork, clock: FrozenClock
) -> None:
    """7. 日界未勾差事 → expired；库存仍无差事。"""
    with uow.transaction():
        ensure_settled(clock, uow)
        plan = planner.add_errand(TODAY, "未勾差事")
        eid = _eid(plan)
    clock.set("2026-08-31T12:00:00+08:00")
    with uow.transaction():
        ensure_settled(clock, uow)
    sealed = planner.open_day(TODAY)
    assert sealed.status == "sealed"
    errand = next(e for e in sealed.errands if e.id == eid)
    assert errand.status == "expired"
    assert planner.list_inventory() == []


def test_completed_errand_stays_completed_not_expired(
    planner: Planner, uow: UnitOfWork, clock: FrozenClock
) -> None:
    """8. 差事已勾 → 仍 completed，不是 expired。"""
    with uow.transaction():
        ensure_settled(clock, uow)
        plan = planner.add_errand(TODAY, "已勾差事")
        eid = _eid(plan)
        planner.complete_errand(eid)
    clock.set("2026-08-31T12:00:00+08:00")
    with uow.transaction():
        ensure_settled(clock, uow)
    sealed = planner.open_day(TODAY)
    errand = next(e for e in sealed.errands if e.id == eid)
    assert errand.status == "completed"
    assert errand.completed_at is not None


def test_midnight_boundary_seals_previous_day(
    planner: Planner, uow: UnitOfWork, clock: FrozenClock
) -> None:
    """14. 午夜边界 冻结 23:59+08 写一条；拨到 00:01+08；ensure_settled；旧日封印。"""
    clock.set("2026-08-30T23:59:00+08:00")
    assert clock.today() == TODAY
    with uow.transaction():
        ensure_settled(clock, uow)
        plan = planner.add_todo_on_day(TODAY, "午夜前")
        tid = _tid(plan)
    clock.set("2026-08-31T00:01:00+08:00")
    assert clock.today() == TOMORROW
    with uow.transaction():
        ensure_settled(clock, uow)
    old = planner.open_day(TODAY)
    assert old.status == "sealed"
    assert old.todos[0].task_id == tid
    assert old.todos[0].completed_on_day is False
    assert tid in _inv_ids(planner)
    assert uow.meta.get("last_settled_date") == TOMORROW


def test_skipping_three_days_seals_middle_and_returns_task(
    planner: Planner, uow: UnitOfWork, clock: FrozenClock
) -> None:
    """16. 跳过 3 天 预排在中间那天，三天后打开，中间那天封印、任务回库存、今天干净。"""
    with uow.transaction():
        ensure_settled(clock, uow)
        middle = planner.add_todo_on_day(MIDDLE, "中间预排")
        mid_id = _tid(middle)
        future = planner.add_todo_on_day(SKIP_TO, "仍是今天")
        future_id = _tid(future)
    clock.set("2026-09-02T12:00:00+08:00")
    assert clock.today() == SKIP_TO
    with uow.transaction():
        ensure_settled(clock, uow)
    sealed_middle = planner.open_day(MIDDLE)
    assert sealed_middle.status == "sealed"
    assert sealed_middle.todos[0].task_id == mid_id
    assert sealed_middle.todos[0].completed_on_day is False
    assert mid_id in _inv_ids(planner)
    today = planner.open_day(SKIP_TO)
    assert today.status == "open"
    assert [e.task_id for e in today.todos] == [future_id]
    assert future_id not in _inv_ids(planner)
    assert planner.get_task(future_id).current_scheduled_date == SKIP_TO
    assert uow.meta.get("last_settled_date") == SKIP_TO
    assert uow.get_day("2026-09-01") is None


def test_ensure_settled_is_idempotent(
    planner: Planner, uow: UnitOfWork, clock: FrozenClock
) -> None:
    """17. 幂等结转 ensure_settled 连开两次，水位与行数不变。"""
    with uow.transaction():
        ensure_settled(clock, uow)
        plan = planner.add_todo_on_day(TODAY, "幂等待办")
        tid = _tid(plan)
        planner.add_errand(TODAY, "幂等差事")
    clock.set("2026-08-31T12:00:00+08:00")
    with uow.transaction():
        ensure_settled(clock, uow)
    first_day = planner.open_day(TODAY)
    first_inv = _inv_ids(planner)
    first_water = uow.meta.get("last_settled_date")
    with uow.transaction():
        ensure_settled(clock, uow)
    second_day = planner.open_day(TODAY)
    assert first_water == uow.meta.get("last_settled_date") == TOMORROW
    assert first_day.status == second_day.status == "sealed"
    assert first_day.sealed_at == second_day.sealed_at
    assert [e.task_id for e in first_day.todos] == [e.task_id for e in second_day.todos]
    assert [e.status for e in first_day.errands] == [e.status for e in second_day.errands]
    assert first_inv == _inv_ids(planner) == {tid}


def test_crash_inside_transaction_leaves_watermark_unchanged(
    tmp_path: Path, clock: FrozenClock
) -> None:
    """18. 结转中崩溃 事务中途 raise，水位停在旧值，数据无半封印。"""
    uow = SqliteUnitOfWork.open(tmp_path / "crash.sqlite")
    try:
        planner = Planner(clock=clock, uow=uow)
        with uow.transaction():
            ensure_settled(clock, uow)
            plan = planner.add_todo_on_day(TODAY, "应回滚")
            tid = _tid(plan)
            planner.add_errand(TODAY, "未过期")
        assert uow.meta.get("last_settled_date") == TODAY
        clock.set("2026-08-31T12:00:00+08:00")
        crashing = _CrashOnSeal(uow)
        with pytest.raises(RuntimeError, match="crash during settle"):
            with crashing.transaction():
                ensure_settled(clock, crashing)
        assert uow.meta.get("last_settled_date") == TODAY
        rec = uow.get_day(TODAY)
        assert rec is not None
        assert rec.status == "open"
        assert rec.sealed_at is None
        assert planner.get_task(tid).current_scheduled_date == TODAY
        assert tid not in _inv_ids(planner)
        assert planner.open_day(TODAY).errands[0].status == "open"
    finally:
        uow.close()


def test_clock_rewind_does_not_unseal(
    planner: Planner, uow: UnitOfWork, clock: FrozenClock
) -> None:
    """19. 时钟回拨 封印后 today 回到昨天，写昨天仍 409。"""
    with uow.transaction():
        ensure_settled(clock, uow)
        planner.add_todo_on_day(TODAY, "已封印")
    clock.set("2026-08-31T12:00:00+08:00")
    with uow.transaction():
        ensure_settled(clock, uow)
    assert uow.meta.get("last_settled_date") == TOMORROW
    assert planner.open_day(TODAY).status == "sealed"
    clock.set("2026-08-30T12:00:00+08:00")
    assert clock.today() == TODAY
    with uow.transaction():
        ensure_settled(clock, uow)
    assert uow.meta.get("last_settled_date") == TOMORROW
    assert planner.open_day(TODAY).status == "sealed"
    with pytest.raises(DaySealed):
        planner.add_todo_on_day(TODAY, "回拨补写")


def test_first_empty_db_watermark_is_today_without_forging_past_days(
    planner: Planner, uow: UnitOfWork, clock: FrozenClock
) -> None:
    """29. 首次空库水位 last_settled_date == today，不伪造安装前的封印空日。"""
    assert uow.is_proven_empty()
    assert uow.meta.get("last_settled_date") is None
    with uow.transaction():
        ensure_settled(clock, uow)
    assert uow.meta.get("last_settled_date") == TODAY
    assert uow.get_day(YESTERDAY) is None
    assert uow.get_day(TODAY) is None
    assert uow.is_proven_empty()
    assert planner.open_day(TODAY).todos == []
    assert planner.list_inventory() == []


def test_restore_missing_watermark_seals_existing_open_days(
    planner: Planner, uow: UnitOfWork, clock: FrozenClock
) -> None:
    """32. 恢复路径缺水位：已有 open 昨天、meta 无 last_settled_date → 必须封印。"""
    clock.set("2026-08-29T12:00:00+08:00")
    with uow.transaction():
        plan = planner.add_todo_on_day(YESTERDAY, "恢复路径")
        tid = _tid(plan)
        planner.add_errand(YESTERDAY, "昨天差事")
    assert uow.meta.get("last_settled_date") is None
    assert uow.get_day(YESTERDAY) is not None
    assert uow.get_day(YESTERDAY).status == "open"
    clock.set(FROZEN)
    assert clock.today() == TODAY
    with uow.transaction():
        ensure_settled(clock, uow)
    sealed = planner.open_day(YESTERDAY)
    assert sealed.status == "sealed"
    assert sealed.todos[0].task_id == tid
    assert sealed.todos[0].completed_on_day is False
    assert sealed.errands[0].status == "expired"
    assert tid in _inv_ids(planner)
    assert uow.meta.get("last_settled_date") == TODAY
    assert planner.open_day(TODAY).todos == []


class _CrashOnSeal:
    """Proxy that commits the seal write then raises, so the txn must roll back."""

    def __init__(self, inner: SqliteUnitOfWork) -> None:
        self._inner = inner

    def save_day(self, day: DayRecord) -> None:
        self._inner.save_day(day)
        if day.status == "sealed":
            raise RuntimeError("crash during settle")

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)
