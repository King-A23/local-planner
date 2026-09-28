"""The Agent CLI exposes goal writes with explicit concurrency values."""

from __future__ import annotations


def test_goal_cli_create_read_and_schedule_next(planner_home, run_cli) -> None:
    code, created, _ = run_cli([
        "goal", "create", "--title", "通过 CSP", "--notes", "算法", "--horizon-text", "明年",
        "--request-id", "goal-1", "--recovery-generation", "none",
    ])
    assert code == 0
    goal = created["data"]
    assert goal["title"] == "通过 CSP"
    assert goal["recoveryGeneration"] is None

    code, added, _ = run_cli([
        "goal", "add-task", goal["id"], "--title", "刷一套题", "--request-id", "task-1",
        "--expected-revision", str(goal["revision"]), "--recovery-generation", "none",
    ])
    assert code == 0
    with_task = added["data"]
    task_id = with_task["tasks"][0]["taskId"]

    code, selected, _ = run_cli([
        "goal", "next", goal["id"], "--task-id", task_id,
        "--expected-revision", str(with_task["revision"]), "--recovery-generation", "none",
    ])
    assert code == 0
    assert selected["data"]["nextTaskId"] == task_id

    code, scheduled, _ = run_cli([
        "goal", "schedule-next", goal["id"], "--expected-task-id", task_id,
        "--expected-scheduled-date", "none",
        "--expected-revision", str(selected["data"]["revision"]), "--recovery-generation", "none",
    ])
    assert code == 0
    assert scheduled["data"]["tasks"][0]["scheduledDate"] == "2026-08-31"


def test_goal_cli_write_requires_recovery_generation(planner_home, run_cli) -> None:
    code, payload, _ = run_cli([
        "goal", "create", "--title", "缺少 generation", "--request-id", "goal-1",
    ])
    assert code == 2
    assert payload["error"]["code"] == "UsageError"
