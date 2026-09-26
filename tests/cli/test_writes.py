from __future__ import annotations

TODAY = "2026-08-31"
YESTERDAY = "2026-08-30"


def test_add_complete_plan_item_has_stable_id(planner_home, run_cli):
    code, added, _ = run_cli(
        ["day", "todo", "add", "today", "--title", "写完今天计划"]
    )
    assert code == 0
    todos = added["data"]["todos"]
    assert len(todos) == 1
    task_id = todos[0]["taskId"]
    assert todos[0]["title"] == "写完今天计划"
    assert todos[0]["completedOnDay"] is False

    code, listed, _ = run_cli(["inventory", "list"])
    assert listed["data"]["items"] == []

    code, done, _ = run_cli(["day", "todo", "complete", TODAY, task_id])
    assert code == 0
    assert done["data"]["todos"][0]["completedOnDay"] is True
    assert done["data"]["todos"][0]["taskId"] == task_id


def test_past_day_write_fails_and_leaves_store_unchanged(planner_home, run_cli):
    code, before, _ = run_cli(["day", "open", YESTERDAY])
    assert code == 0
    assert before["data"]["writable"] is False
    assert before["data"]["todos"] == []

    code, failed, _ = run_cli(
        ["day", "todo", "add", YESTERDAY, "--title", "不该写进去"]
    )
    assert code == 1
    assert failed["ok"] is False
    assert failed["error"]["code"] == "DaySealed"
    assert failed["today"] == TODAY

    code, after, _ = run_cli(["day", "open", YESTERDAY])
    assert after["data"]["todos"] == []
    assert after["data"]["errands"] == []


def test_errand_add_and_schedule_from_todo(planner_home, run_cli):
    code, inv, _ = run_cli(["inventory", "add", "--title", "周四答辩"])
    task_id = inv["data"]["taskId"]
    code, planned, _ = run_cli(["task", "schedule", task_id, "--date", TODAY])
    assert code == 0
    assert planned["data"]["todos"][0]["taskId"] == task_id

    code, errand, _ = run_cli(
        ["day", "errand", "add", "today", "--title", "打印材料"]
    )
    assert code == 0
    assert errand["data"]["errands"][0]["title"] == "打印材料"
    assert errand["data"]["errands"][0]["id"]
