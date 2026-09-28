"""Agent workflows through the actual parser, transactions, SQLite and JSON contract."""
from __future__ import annotations

import pytest

from local_planner.agent_receipts import build_agent_receipt

TODAY = "2026-08-31"
NEXT = "2026-09-01"


def invoke(run_cli, *args):
    code, result, _ = run_cli(list(args))
    assert code == 0, result
    assert result["ok"]
    return result["data"]


def edit_args(kind, item, *changes):
    return [kind, "edit", item.get("taskId", item.get("id")), *changes,
            "--expected-title", item["title"], "--expected-notes", item["notes"]]


def test_notes_edit_search_clear_and_conflict_are_atomic(planner_home, run_cli):
    item = invoke(run_cli, "inventory", "add", "--title", "报告")
    changed = invoke(run_cli, *edit_args("task", item, "--title", "周报", "--notes", "Review 材料\n第二行"))
    assert changed["notes"] == "Review 材料\n第二行"
    found = invoke(run_cli, "search", "--query", "review 第二行")
    assert found["total"] == 1 and found["items"][0]["id"] == item["taskId"]
    code, stale, _ = run_cli(edit_args("task", item, "--notes", "旧草稿"))
    assert code == 1 and stale["error"]["code"] == "Conflict"
    before = invoke(run_cli, "context")
    cleared = invoke(run_cli, *edit_args("task", changed, "--clear-notes"))
    assert cleared["title"] == "周报" and cleared["notes"] == ""
    receipt = build_agent_receipt(before, invoke(run_cli, "context"))
    assert receipt["counts"] == {"notes_changed": 1}


@pytest.mark.parametrize("kind", ["task", "errand"])
def test_edit_validation_and_history_cannot_be_bypassed(planner_home, run_cli, monkeypatch, kind):
    section = "todos" if kind == "task" else "errands"
    row = invoke(run_cli, "day", "todo" if kind == "task" else "errand", "add", "today", "--title", "原始")[section][0]
    code, error, _ = run_cli(edit_args(kind, row, "--title", "不能部分保存", "--notes", "a" * 10001))
    assert code == 1 and error["error"]["code"] == "ValidationError"
    current = invoke(run_cli, "day", "open", "today")[section][0]
    assert (current["title"], current["notes"]) == ("原始", "")
    changed = invoke(run_cli, *edit_args(kind, row, "--notes", "材料"))[section][0]
    if kind == "task":
        invoke(run_cli, "day", "todo", "complete", "today", row["taskId"])
    monkeypatch.setenv("LOCAL_PLANNER_CLOCK", "2026-09-01T08:00:00+08:00")
    code, sealed, _ = run_cli(edit_args(kind, changed, "--notes", "不允许"))
    assert code == 1 and sealed["error"]["code"] == "DaySealed"
    assert invoke(run_cli, "day", "open", TODAY)[section][0]["notes"] == "材料"


def test_edit_requires_explicit_changes_and_expected_values(planner_home, run_cli):
    item = invoke(run_cli, "inventory", "add", "--title", "事项")
    for args in (["task", "edit", item["taskId"], "--notes", "内容"],
                 edit_args("task", item), edit_args("task", item, "--notes", "内容", "--clear-notes")):
        code, result, _ = run_cli(args)
        assert code == 2 and result["error"]["code"] == "UsageError"
    assert invoke(run_cli, "inventory", "list")["items"] == [item]


@pytest.mark.parametrize("kind,section,id_key,manual_key", [
    ("todo", "todos", "taskId", "manualTodoOrder"),
    ("errand", "errands", "id", "manualErrandOrder"),
])
def test_reorder_includes_completed_and_can_restore_automatic(planner_home, run_cli, kind, section, id_key, manual_key):
    late = invoke(run_cli, "day", kind, "add", "tomorrow", "--title", "晚些", "--start", "15:00")[section][0]
    rows = invoke(run_cli, "day", kind, "add", "tomorrow", "--title", "较早", "--start", "09:00")[section]
    early = next(row for row in rows if row[id_key] != late[id_key])
    if kind == "todo":
        invoke(run_cli, "day", "todo", "complete", "tomorrow", early[id_key])
    else:
        invoke(run_cli, "errand", "complete", early[id_key])
    code, missing, _ = run_cli(["day", kind, "reorder", "tomorrow", late[id_key]])
    assert code == 1 and missing["error"]["code"] == "Conflict"
    before = invoke(run_cli, "context")
    manual = invoke(run_cli, "day", kind, "reorder", "tomorrow", late[id_key], early[id_key])
    assert manual[manual_key] and [row[id_key] for row in manual[section]] == [late[id_key], early[id_key]]
    assert build_agent_receipt(before, invoke(run_cli, "context"))["counts"] == {"order_changed": 1}
    before = invoke(run_cli, "context")
    automatic = invoke(run_cli, "day", kind, "reorder", "tomorrow", "--automatic")
    assert not automatic[manual_key] and [row[id_key] for row in automatic[section]] == [early[id_key], late[id_key]]
    assert build_agent_receipt(before, invoke(run_cli, "context"))["counts"] == {"order_changed": 1}
    code, bad, _ = run_cli(["day", kind, "reorder", "tomorrow", late[id_key], "--automatic"])
    assert code == 2 and bad["error"]["code"] == "UsageError"
    code, past, _ = run_cli(["day", kind, "reorder", "2026-08-30", "--automatic"])
    assert code == 1 and past["error"]["code"] == "DaySealed"


def test_future_completion_notes_and_clocks_have_accurate_receipts(planner_home, run_cli):
    row = invoke(run_cli, "day", "todo", "add", "tomorrow", "--title", "未来的事", "--start", "09:00")["todos"][0]
    before = invoke(run_cli, "context")
    invoke(run_cli, *edit_args("task", row, "--notes", "未来备注"))
    invoke(run_cli, "day", "todo", "time", "tomorrow", row["taskId"], "--end", "10:00")
    invoke(run_cli, "day", "todo", "complete", "tomorrow", row["taskId"])
    after = invoke(run_cli, "context")
    assert after["scheduledAhead"] == []  # Older compact contract remains compatible.
    complete = after["daysAhead"][0]["todos"][0]
    assert complete["completedOnDay"] and complete["notes"] == "未来备注"
    assert (complete["startClock"], complete["endClock"]) == ("09:00", "10:00")
    assert build_agent_receipt(before, after)["counts"] == {"completed": 1, "clock_changed": 1, "notes_changed": 1}
    invoke(run_cli, "day", "todo", "uncomplete", "tomorrow", row["taskId"])
    assert build_agent_receipt(after, invoke(run_cli, "context"))["counts"] == {"completion_undone": 1}


def test_inventory_completion_and_restore_use_server_today(planner_home, run_cli):
    item = invoke(run_cli, "inventory", "add", "--title", "待办完成")
    before = invoke(run_cli, "context")
    plan = invoke(run_cli, "inventory", "complete", item["taskId"])
    assert plan["date"] == TODAY and plan["todos"][0]["completedOnDay"]
    assert build_agent_receipt(before, invoke(run_cli, "context"))["counts"] == {"todo_to_today": 1, "completed": 1}
    assert invoke(run_cli, "search", "--query", "待办完成")["total"] == 0
    invoke(run_cli, "day", "todo", "uncomplete", "today", item["taskId"])
    invoke(run_cli, "task", "unschedule", item["taskId"])
    assert invoke(run_cli, "inventory", "list")["items"][0]["taskId"] == item["taskId"]


def test_tomorrow_reschedule_preserves_details_and_tracks_clock_rollover(planner_home, run_cli, monkeypatch):
    row = invoke(run_cli, "day", "todo", "add", "today", "--title", "改期", "--start", "09:00")["todos"][0]
    invoke(run_cli, *edit_args("task", row, "--notes", "不要遗失"))
    moved = invoke(run_cli, "task", "schedule", row["taskId"], "--date", "tomorrow")
    assert moved["date"] == NEXT
    assert (moved["todos"][0]["notes"], moved["todos"][0]["startClock"]) == ("不要遗失", "09:00")
    assert invoke(run_cli, "day", "open", "today")["todos"] == []
    monkeypatch.setenv("LOCAL_PLANNER_CLOCK", "2026-09-01T08:00:00+08:00")
    assert invoke(run_cli, "task", "schedule", row["taskId"], "--date", "tomorrow")["date"] == "2026-09-02"


def test_capabilities_search_limits_and_context_do_not_generate_future_days(planner_home, run_cli):
    caps = invoke(run_cli, "capabilities")
    context = invoke(run_cli, "context")
    assert context["capabilities"] == caps
    assert {command["name"] for command in caps["commands"]} >= {"search", "task.edit", "errand.edit", "inventory.complete", "day.todo.reorder"}
    assert caps["limits"]["notes"] == 10000 and "tomorrow" in caps["dateTokens"]
    invoke(run_cli, "recurrence", "add", "--kind", "plan", "--title", "未来每日", "--frequency", "daily", "--start-date", "tomorrow")
    assert invoke(run_cli, "context")["daysAhead"] == []
    code, too_long, _ = run_cli(["search", "--query", "a" * 201])
    assert code == 1 and too_long["error"]["code"] == "ValidationError"
    assert invoke(run_cli, "search", "--query", " ")["items"] == []
