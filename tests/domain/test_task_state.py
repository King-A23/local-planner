"""Domain command tests for PR 2. Sealed writes call seal_day, not ensure_settled."""

from __future__ import annotations

from dataclasses import replace

import pytest

from local_planner.clock import FrozenClock, shanghai_date
from local_planner.domain.commands import Planner
from local_planner.domain.errors import Conflict, DaySealed, NotFound, ValidationError
from local_planner.domain.models import DayRecord, DayTaskEntry, is_writable, task_status

TODAY = "2026-08-30"
YESTERDAY = "2026-08-29"
FUTURE = "2026-08-31"
F2 = "2026-09-01"
FROZEN = "2026-08-30T12:00:00+08:00"


@pytest.fixture
def planner() -> Planner:
    return Planner(clock=FrozenClock(FROZEN))


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


def _inv_titles(p: Planner) -> list[str]:
    return [item.task.title for item in p.list_inventory()]


def test_d12_add_todo_on_today_not_in_inventory(planner: Planner) -> None:
    """1. D12 今天写下正经待办 → 库存不含它；当天列表含它。"""
    plan = planner.add_todo_on_day(TODAY, "把设计文档写完")
    assert [e.title_snapshot for e in plan.todos] == ["把设计文档写完"]
    assert _inv_titles(planner) == []
    task = planner.get_task(_tid(plan))
    assert task.current_scheduled_date == TODAY
    assert task_status(task) == "scheduled"


def test_inventory_only_does_not_appear_on_today(planner: Planner) -> None:
    """2. 仅入库 → OpenDay(today) 不含它。"""
    item = planner.add_to_inventory("竞赛报名")
    today = planner.open_day(TODAY)
    assert today.todos == []
    assert item.task.id in _inv_ids(planner)
    assert item.task.current_scheduled_date is None
    assert task_status(item.task) == "inventory"


def test_schedule_to_today_moves_out_of_inventory(planner: Planner) -> None:
    """3. 排到今天 → 库存消失，今天出现，同一 task_id。"""
    item = planner.add_to_inventory("抽到今天")
    tid = item.task.id
    plan = planner.schedule_to_date(tid, TODAY)
    assert plan.todos[0].task_id == tid
    assert plan.todos[0].title_snapshot == "抽到今天"
    assert tid not in _inv_ids(planner)


def test_schedule_to_future_not_on_today(planner: Planner) -> None:
    """4. 排到未来 F → 今天不含；OpenDay(F) 含（不测水位把 today 变成 F）。"""
    item = planner.add_to_inventory("预排未来")
    tid = item.task.id
    planner.schedule_to_date(tid, FUTURE)
    assert all(e.task_id != tid for e in planner.open_day(TODAY).todos)
    future = planner.open_day(FUTURE)
    assert [e.task_id for e in future.todos] == [tid]
    assert is_writable(future, planner.clock.today())
    assert tid not in _inv_ids(planner)


def test_cross_day_identity_uncompleted_then_completed(planner: Planner) -> None:
    """9. 同一 id 出现在 D1 未勾快照与 D3 已勾快照。"""
    d1 = planner.add_todo_on_day(FUTURE, "长期任务")
    tid = _tid(d1)
    planner.seal_day(FUTURE)
    planner.schedule_to_date(tid, F2)
    planner.complete_task_on_day(tid, F2)
    snap_d1 = planner.open_day(FUTURE).todos[0]
    snap_d3 = planner.open_day(F2).todos[0]
    assert snap_d1.task_id == snap_d3.task_id == tid
    assert snap_d1.completed_on_day is False
    assert snap_d3.completed_on_day is True
    assert tid not in _inv_ids(planner)


def test_sealed_day_rejects_all_writes(planner: Planner) -> None:
    """10. 过去/封印日写全部 409：勾选、加待办、加差事、改名 entry、删除、排序。"""
    with pytest.raises(DaySealed):
        planner.add_todo_on_day(YESTERDAY, "补昨天")
    with pytest.raises(DaySealed):
        planner.add_errand(YESTERDAY, "补差事")

    day = planner.add_todo_on_day(TODAY, "待办")
    tid = _tid(day)
    day = planner.add_errand(TODAY, "差事")
    eid = _eid(day, "差事")
    planner.seal_day(TODAY)

    with pytest.raises(DaySealed):
        planner.complete_task_on_day(tid, TODAY)
    with pytest.raises(DaySealed):
        planner.add_todo_on_day(TODAY, "又一条")
    with pytest.raises(DaySealed):
        planner.add_errand(TODAY, "又差事")
    with pytest.raises(DaySealed):
        planner.rename_errand(eid, "改差事")
    with pytest.raises(DaySealed):
        planner.delete_errand(eid)
    with pytest.raises(DaySealed):
        planner.reorder_todos(TODAY, [tid])
    with pytest.raises(DaySealed):
        planner.reorder_errands(TODAY, [eid])
    with pytest.raises(DaySealed):
        planner.complete_errand(eid)


def test_future_day_is_writable(planner: Planner) -> None:
    """11. 未来日可写：新建、勾选、改排。"""
    plan = planner.add_todo_on_day(FUTURE, "未来新建")
    tid = _tid(plan)
    plan = planner.complete_task_on_day(tid, FUTURE)
    assert plan.todos[0].completed_on_day is True
    planner.uncomplete_task_on_day(tid, FUTURE)
    moved = planner.schedule_to_date(tid, F2)
    assert all(e.task_id != tid for e in planner.open_day(FUTURE).todos)
    assert moved.todos[0].task_id == tid


def test_rename_leaves_sealed_snapshot_unchanged(planner: Planner) -> None:
    """12. 改名：已封印日标题不变；库存与未封印日变。"""
    plan = planner.add_todo_on_day(FUTURE, "旧标题")
    tid = _tid(plan)
    planner.seal_day(FUTURE)
    planner.schedule_to_date(tid, TODAY)
    planner.rename_task(tid, "新标题")
    assert planner.open_day(FUTURE).todos[0].title_snapshot == "旧标题"
    assert planner.open_day(TODAY).todos[0].title_snapshot == "新标题"
    assert planner.get_task(tid).title == "新标题"


def test_complete_then_uncomplete_then_seal_returns_to_inventory(
    planner: Planner,
) -> None:
    """13. 完成后再 Uncomplete（仍是今天）回可写今天；随后封印仍未勾则回库存。"""
    plan = planner.add_todo_on_day(TODAY, "当天勾完再取消")
    tid = _tid(plan)
    planner.complete_task_on_day(tid, TODAY)
    assert planner.get_task(tid).current_scheduled_date is None
    assert tid not in _inv_ids(planner)
    planner.uncomplete_task_on_day(tid, TODAY)
    task = planner.get_task(tid)
    assert task.completed_at is None
    assert task.completed_on_date is None
    assert task.current_scheduled_date == TODAY
    assert planner.open_day(TODAY).todos[0].completed_on_day is False
    planner.seal_day(TODAY)
    assert tid in _inv_ids(planner)
    assert planner.open_day(TODAY).todos[0].completed_on_day is False


def test_same_task_cannot_be_scheduled_on_two_open_days(planner: Planner) -> None:
    """20. 同任务同时两天：尝试插入第二行排期，拒绝。"""
    plan = planner.add_todo_on_day(TODAY, "单排期")
    tid = _tid(plan)
    with pytest.raises(Conflict, match="两天"):
        planner.uow.save_entry(
            DayTaskEntry(
                day_date=FUTURE,
                task_id=tid,
                title_snapshot="单排期",
                sort_order=0,
                completed_on_day=False,
            )
        )
    planner.schedule_to_date(tid, FUTURE)
    open_days = []
    for entry in planner.uow.list_entries_for_task(tid):
        rec = planner.uow.get_day(entry.day_date)
        if rec is None or rec.status == "open":
            open_days.append(entry.day_date)
    assert open_days == [FUTURE]
    assert all(e.task_id != tid for e in planner.open_day(TODAY).todos)


def test_delete_without_history_ok_sealed_history_conflict(planner: Planner) -> None:
    """21. 删除：无历史可删；有封印历史 409。"""
    item = planner.add_to_inventory("误建")
    planner.delete_task(item.task.id)
    assert item.task.id not in _inv_ids(planner)

    plan = planner.add_todo_on_day(FUTURE, "有封印历史")
    tid = _tid(plan)
    planner.seal_day(FUTURE)
    with pytest.raises(Conflict, match="过去的某一天还记着它"):
        planner.delete_task(tid)
    assert planner.open_day(FUTURE).todos[0].task_id == tid


def test_title_validation(planner: Planner) -> None:
    """22. 标题空、纯空格、201 字 → 400。"""
    for bad in ("", "   ", "a" * 201):
        with pytest.raises(ValidationError):
            planner.add_todo_on_day(TODAY, bad)
        with pytest.raises(ValidationError):
            planner.add_to_inventory(bad)
        with pytest.raises(ValidationError):
            planner.add_errand(TODAY, bad)
    plan = planner.add_todo_on_day(TODAY, "a" * 200)
    assert len(plan.todos[0].title_snapshot) == 200
    stripped = planner.add_to_inventory("  两端空白  ")
    assert stripped.task.title == "两端空白"


def test_unschedule_returns_to_inventory(planner: Planner) -> None:
    """24. Unschedule：可写日移回库存；今天列表消失；库存出现同一 id。"""
    plan = planner.add_todo_on_day(TODAY, "排错天")
    tid = _tid(plan)
    item = planner.unschedule(tid)
    assert item.task.id == tid
    assert planner.open_day(TODAY).todos == []
    assert tid in _inv_ids(planner)


def test_reschedule_writable_d1_to_d2(planner: Planner) -> None:
    """25. 可写日 D1→D2 改排：D1 无 entry，D2 有，title_snapshot=tasks.title，sort=max+1。"""
    planner.add_todo_on_day(F2, "已在 D2")
    d1 = planner.add_todo_on_day(FUTURE, "旧名")
    tid = _tid(d1)
    planner.rename_task(tid, "当前标题")
    plan = planner.schedule_to_date(tid, F2)
    assert all(e.task_id != tid for e in planner.open_day(FUTURE).todos)
    moved = next(e for e in plan.todos if e.task_id == tid)
    assert moved.title_snapshot == "当前标题"
    assert moved.sort_order == 1
    assert planner.get_task(tid).title == "当前标题"


def test_complete_on_future_day_uses_plan_date(planner: Planner) -> None:
    """26. 冻结 2026-08-30，Complete 在 8-31：completed_on_date=8-31，快照已勾。"""
    plan = planner.add_todo_on_day(FUTURE, "提前完成")
    tid = _tid(plan)
    planner.complete_task_on_day(tid, FUTURE)
    task = planner.get_task(tid)
    assert task.completed_on_date == FUTURE
    assert shanghai_date(task.completed_at) == TODAY
    assert planner.open_day(FUTURE).todos[0].completed_on_day is True
    assert tid not in _inv_ids(planner)
    assert task.current_scheduled_date is None
    assert task_status(task) == "completed"


def test_virtual_empty_past_day_is_read_only(planner: Planner) -> None:
    """30. OpenDay(昨天) 无行：空列表、writable=false、读成功；写入 409 DaySealed。"""
    plan = planner.open_day(YESTERDAY)
    assert plan.todos == []
    assert plan.errands == []
    assert plan.status == "sealed"
    assert is_writable(plan, TODAY) is False
    with pytest.raises(DaySealed):
        planner.add_todo_on_day(YESTERDAY, "写昨天")
    with pytest.raises(DaySealed):
        planner.add_errand(YESTERDAY, "写昨天差事")


def test_complete_requires_current_scheduled_date_equals_d(planner: Planner) -> None:
    """Complete 前提：current_scheduled_date == D，禁止靠第二行 entry 完成别日任务。"""
    plan = planner.add_todo_on_day(TODAY, "错位完成")
    tid = _tid(plan)
    task = planner.get_task(tid)
    planner.uow.save_task(replace(task, current_scheduled_date=FUTURE))
    planner.uow.save_day(DayRecord(date=FUTURE, status="open", sealed_at=None))
    with pytest.raises(Conflict, match="未排在这一天"):
        planner.complete_task_on_day(tid, TODAY)


def test_seal_day_returns_unfinished_todos_and_expires_errands(
    planner: Planner,
) -> None:
    unfinished = planner.add_todo_on_day(TODAY, "未完成待办")
    uid = _tid(unfinished)
    done = planner.add_todo_on_day(TODAY, "已勾待办")
    did = _tid(done, "已勾待办")
    planner.complete_task_on_day(did, TODAY)
    planner.add_errand(TODAY, "未勾差事")
    done_e = planner.add_errand(TODAY, "已勾差事")
    eid = _eid(done_e, "已勾差事")
    planner.complete_errand(eid)

    planner.seal_day(TODAY)
    sealed = planner.open_day(TODAY)
    assert sealed.status == "sealed"
    assert sealed.sealed_at is not None
    assert is_writable(sealed, TODAY) is False
    assert uid in _inv_ids(planner)
    assert did not in _inv_ids(planner)
    by_title = {e.title: e for e in sealed.errands}
    assert by_title["未勾差事"].status == "expired"
    assert by_title["已勾差事"].status == "completed"
    todos = {e.title_snapshot: e for e in sealed.todos}
    assert todos["未完成待办"].completed_on_day is False
    assert todos["已勾待办"].completed_on_day is True


def test_schedule_completed_task_conflicts(planner: Planner) -> None:
    plan = planner.add_todo_on_day(TODAY, "做完了")
    tid = _tid(plan)
    planner.complete_task_on_day(tid, TODAY)
    with pytest.raises(Conflict):
        planner.schedule_to_date(tid, FUTURE)


def test_invalid_date_is_validation_error(planner: Planner) -> None:
    for bad in ("2026-13-40", "08-30", "2026-8-30", "2026-08-30T00:00:00"):
        with pytest.raises(ValidationError):
            planner.open_day(bad)
        with pytest.raises(ValidationError):
            planner.add_todo_on_day(bad, "x")


def test_year_cap_rejects_far_writes(planner: Planner) -> None:
    with pytest.raises(ValidationError):
        planner.add_todo_on_day("2015-08-30", "太远")
    with pytest.raises(ValidationError):
        planner.add_todo_on_day("2037-08-30", "太远")
    # |year| == 10 is allowed on a still-writable future day
    planner.add_todo_on_day("2036-08-30", "边界")


def test_reorder_todos_and_errands(planner: Planner) -> None:
    planner.add_todo_on_day(TODAY, "A")
    planner.add_todo_on_day(TODAY, "B")
    ids = [_tid(planner.open_day(TODAY), "A"), _tid(planner.open_day(TODAY), "B")]
    plan = planner.reorder_todos(TODAY, list(reversed(ids)))
    assert [e.title_snapshot for e in plan.todos] == ["B", "A"]
    with pytest.raises(Conflict):
        planner.reorder_todos(TODAY, ids + ["missing"])

    planner.add_errand(TODAY, "e1")
    planner.add_errand(TODAY, "e2")
    eids = [_eid(planner.open_day(TODAY), "e1"), _eid(planner.open_day(TODAY), "e2")]
    plan = planner.reorder_errands(TODAY, list(reversed(eids)))
    assert [e.title for e in plan.errands] == ["e2", "e1"]


def test_unknown_task_and_errand_not_found(planner: Planner) -> None:
    with pytest.raises(NotFound):
        planner.complete_task_on_day("no-such-task", TODAY)
    with pytest.raises(NotFound):
        planner.complete_errand("no-such-errand")


def test_seal_day_is_idempotent(planner: Planner) -> None:
    planner.add_todo_on_day(TODAY, "x")
    planner.seal_day(TODAY)
    first = planner.open_day(TODAY)
    planner.seal_day(TODAY)
    second = planner.open_day(TODAY)
    assert first.status == second.status == "sealed"
    assert first.sealed_at == second.sealed_at
