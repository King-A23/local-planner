from __future__ import annotations

from copy import deepcopy

from local_planner.agent_receipts import build_agent_receipt

TODAY = "2026-08-31"


def _context() -> dict:
    return {
        "today": TODAY,
        "timezone": "Asia/Shanghai",
        "todos": [],
        "errands": [],
        "inventory": [],
        "scheduledAhead": [],
        "errandsAhead": [],
        "recurrences": [],
    }


def test_notes_receipts_cover_inventory_plan_and_errand_without_inventing_missing_values():
    before = _context()
    before["todos"] = [dict(_plan("p", "计划"), notes="")]
    before["inventory"] = [dict(_todo("t", "待办"), notes="旧备注")]
    before["errands"] = [dict(_errand("e", "小事"), notes="内容")]
    after = deepcopy(before)
    after["todos"][0]["notes"] = "补充"
    after["inventory"][0]["notes"] = ""
    after["errands"][0]["notes"] = "新的内容"
    receipt = build_agent_receipt(before, after)
    assert receipt["counts"] == {"notes_changed": 3}
    assert {change["entity"] for change in receipt["changes"]} == {"plan", "todo", "errand"}
    del before["todos"][0]["notes"]
    assert build_agent_receipt(before, after)["counts"] == {"notes_changed": 2}


def test_order_receipts_ignore_added_removed_members_and_automatic_clock_order():
    before = _context()
    before["manualTodoOrder"] = False
    before["todos"] = [_plan("a", "甲"), _plan("b", "乙")]
    after = deepcopy(before)
    after["todos"].reverse()
    assert not build_agent_receipt(before, after)["changed"]
    before["manualTodoOrder"] = after["manualTodoOrder"] = True
    assert build_agent_receipt(before, after)["counts"] == {"order_changed": 1}
    after["todos"] = [_plan("a", "甲"), _plan("new", "新事项")]
    assert "order_changed" not in build_agent_receipt(before, after)["counts"]


def _todo(task_id: str, title: str, target: str | None = None) -> dict:
    return {
        "taskId": task_id,
        "title": title,
        "createdAt": "2026-08-31T00:00:00Z",
        "targetDate": target,
    }


def _plan(
    task_id: str,
    title: str,
    *,
    completed: bool = False,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    return {
        "taskId": task_id,
        "title": title,
        "completedOnDay": completed,
        "sortOrder": 0,
        "startClock": start,
        "endClock": end,
    }


def _errand(
    errand_id: str,
    title: str,
    *,
    status: str = "open",
    start: str | None = None,
    end: str | None = None,
) -> dict:
    return {
        "id": errand_id,
        "title": title,
        "status": status,
        "sortOrder": 0,
        "startClock": start,
        "endClock": end,
    }


def test_added_entities_and_stable_summary() -> None:
    before = _context()
    after = _context()
    after["todos"] = [_plan("p1", "写方案")]
    after["errands"] = [_errand("e1", "取快递")]
    after["inventory"] = [_todo("t1", "以后处理")]

    assert build_agent_receipt(before, after) == {
        "summary": "新增 Plan 1 项；新增 Errand 1 项；新增 To Do 1 项",
        "changed": True,
        "counts": {"plan_added": 1, "errand_added": 1, "todo_added": 1},
        "changes": [
            {
                "type": "plan_added",
                "entity": "plan",
                "id": "p1",
                "title": "写方案",
                "date": TODAY,
            },
            {
                "type": "errand_added",
                "entity": "errand",
                "id": "e1",
                "title": "取快递",
                "date": TODAY,
            },
            {
                "type": "todo_added",
                "entity": "todo",
                "id": "t1",
                "title": "以后处理",
            },
        ],
    }


def test_task_moves_cover_today_inventory_and_future_reschedule() -> None:
    before = _context()
    before["inventory"] = [
        _todo("today", "今天做"),
        _todo("future", "以后做"),
    ]
    before["todos"] = [_plan("back", "移回库存"), _plan("move", "改排")]

    after = _context()
    after["todos"] = [_plan("today", "今天做")]
    after["inventory"] = [_todo("back", "移回库存")]
    after["scheduledAhead"] = [
        {"taskId": "future", "title": "以后做", "date": "2026-09-02"},
        {"taskId": "move", "title": "改排", "date": "2026-09-03"},
    ]

    receipt = build_agent_receipt(before, after)
    assert receipt["summary"] == (
        "To Do 加入今天 1 项；To Do 排入计划 1 项；移回 To Do 1 项；改排 1 项"
    )
    assert receipt["changes"] == [
        {
            "type": "todo_to_today",
            "entity": "plan",
            "id": "today",
            "title": "今天做",
            "toDate": TODAY,
        },
        {
            "type": "todo_scheduled",
            "entity": "plan",
            "id": "future",
            "title": "以后做",
            "toDate": "2026-09-02",
        },
        {
            "type": "moved_to_todo",
            "entity": "todo",
            "id": "back",
            "title": "移回库存",
            "fromDate": TODAY,
        },
        {
            "type": "rescheduled",
            "entity": "plan",
            "id": "move",
            "title": "改排",
            "fromDate": TODAY,
            "toDate": "2026-09-03",
        },
    ]


def test_completion_and_completion_undone_for_plan_and_errand() -> None:
    before = _context()
    before["todos"] = [
        _plan("complete", "完成 Plan"),
        _plan("undo", "取消 Plan", completed=True),
    ]
    before["errands"] = [
        _errand("ec", "完成差事"),
        _errand("eu", "取消差事", status="completed"),
    ]
    after = deepcopy(before)
    after["todos"] = [
        _plan("complete", "完成 Plan", completed=True),
        _plan("undo", "取消 Plan"),
    ]
    after["errands"] = [
        _errand("ec", "完成差事", status="completed"),
        _errand("eu", "取消差事"),
    ]

    receipt = build_agent_receipt(before, after)
    assert receipt["summary"] == "完成 2 项；取消完成 2 项"
    assert [(row["type"], row["entity"], row["id"]) for row in receipt["changes"]] == [
        ("completed", "errand", "ec"),
        ("completed", "plan", "complete"),
        ("completion_undone", "errand", "eu"),
        ("completion_undone", "plan", "undo"),
    ]


def test_rename_clock_and_target_date_changes_do_not_infer_hidden_fields() -> None:
    before = _context()
    before["todos"] = [_plan("p1", "旧名", start="09:00")]
    before["errands"] = [_errand("e1", "买菜", end="18:00")]
    before["inventory"] = [
        _todo("t1", "目标日", "2026-09-01"),
        _todo("moving", "排进今天", "2026-09-05"),
    ]
    after = _context()
    after["todos"] = [
        _plan("p1", "新名", start="10:00", end="11:00"),
        _plan("moving", "排进今天"),
    ]
    after["errands"] = [_errand("e1", "买菜", start="17:00", end="18:00")]
    after["inventory"] = [_todo("t1", "目标日", "2026-09-03")]

    receipt = build_agent_receipt(before, after)
    assert receipt["summary"] == (
        "To Do 加入今天 1 项；改名 1 项；改时钟 2 项；改目标日 1 项"
    )
    assert not any(
        row["type"] in {"clock_changed", "target_date_changed"}
        and row["id"] == "moving"
        for row in receipt["changes"]
    )
    assert {
        (row["type"], row["entity"], row["id"])
        for row in receipt["changes"]
    } == {
        ("todo_to_today", "plan", "moving"),
        ("renamed", "plan", "p1"),
        ("clock_changed", "plan", "p1"),
        ("clock_changed", "errand", "e1"),
        ("target_date_changed", "todo", "t1"),
    }


def test_deletions_and_no_change() -> None:
    before = _context()
    before["todos"] = [_plan("p1", "删 Plan")]
    before["errands"] = [_errand("e1", "删差事")]
    before["inventory"] = [_todo("t1", "删 To Do")]

    receipt = build_agent_receipt(before, _context())
    assert receipt["summary"] == "删除 3 项"
    assert [(row["entity"], row["id"]) for row in receipt["changes"]] == [
        ("errand", "e1"),
        ("plan", "p1"),
        ("todo", "t1"),
    ]

    unchanged = build_agent_receipt(before, deepcopy(before))
    assert unchanged == {
        "summary": "没有发现计划改动",
        "changed": False,
        "counts": {},
        "changes": [],
    }


def test_day_boundary_bucket_change_is_not_reported_as_reschedule() -> None:
    before = _context()
    before["today"] = "2026-08-30"
    before["scheduledAhead"] = [
        {"taskId": "p1", "title": "明天做", "date": TODAY}
    ]
    after = _context()
    after["todos"] = [_plan("p1", "明天做")]

    assert build_agent_receipt(before, after) == {
        "summary": "没有发现计划改动",
        "changed": False,
        "counts": {},
        "changes": [],
    }


def test_missing_optional_context_fields_are_treated_as_empty_or_null() -> None:
    before = {"today": TODAY}
    after = {
        "today": TODAY,
        "todos": [{"taskId": "p1", "title": "无可选字段"}],
        "errands": [{"id": "e1", "title": "无状态字段"}],
    }

    receipt = build_agent_receipt(before, after)
    assert receipt["changed"] is True
    assert receipt["counts"] == {"plan_added": 1, "errand_added": 1}
    assert [row["type"] for row in receipt["changes"]] == [
        "plan_added",
        "errand_added",
    ]


def test_recurrence_create_update_and_state_transitions() -> None:
    before = _context()
    after = _context()
    after["recurrences"] = [
        {
            "id": "r1",
            "title": "吃药",
            "kind": "errand",
            "frequency": "daily",
            "weekdays": [],
            "startDate": TODAY,
            "state": "active",
        }
    ]
    created = build_agent_receipt(before, after)
    assert created["counts"] == {"recurrence_created": 1}

    updated_context = deepcopy(after)
    updated_context["recurrences"][0]["title"] = "晚饭后吃药"
    updated_context["recurrences"][0]["state"] = "paused"
    updated = build_agent_receipt(after, updated_context)
    assert updated["counts"] == {
        "recurrence_updated": 1,
        "recurrence_paused": 1,
    }

    stopped_context = deepcopy(after)
    stopped_context["recurrences"][0]["state"] = "stopped"
    deleted_context = deepcopy(stopped_context)
    deleted_context["recurrences"] = []
    deleted = build_agent_receipt(stopped_context, deleted_context)
    assert deleted["counts"] == {"recurrence_deleted": 1}
    assert deleted["changes"][0]["id"] == "r1"


def test_future_errand_is_included_in_receipt() -> None:
    before = _context()
    after = _context()
    after["errandsAhead"] = [
        {
            "id": "future-errand",
            "title": "明天取件",
            "date": "2026-09-01",
            "status": "open",
            "startClock": "09:00",
            "endClock": None,
        }
    ]

    receipt = build_agent_receipt(before, after)
    assert receipt["counts"] == {"errand_added": 1}
    assert receipt["changes"][0]["date"] == "2026-09-01"
