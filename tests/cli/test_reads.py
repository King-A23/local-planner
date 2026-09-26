from __future__ import annotations

import json

TODAY = "2026-08-31"


def test_meta_json_ok(planner_home, run_cli):
    code, payload, _ = run_cli(["meta"])
    assert code == 0
    assert payload["ok"] is True
    assert payload["v"] == 1
    assert payload["command"] == "meta"
    assert payload["today"] == TODAY
    data = payload["data"]
    assert data["today"] == TODAY
    assert data["timezone"] == "Asia/Shanghai"
    assert data["inventoryCount"] == 0


def test_day_open_today_and_inventory_roundtrip(planner_home, run_cli):
    code, added, _ = run_cli(["inventory", "add", "--title", "竞赛报名"])
    assert code == 0
    task_id = added["data"]["taskId"]
    assert task_id

    code, listed, _ = run_cli(["inventory", "list"])
    assert code == 0
    assert listed["data"]["items"][0]["taskId"] == task_id
    assert listed["data"]["items"][0]["title"] == "竞赛报名"

    code, day, _ = run_cli(["day", "open", "today"])
    assert code == 0
    assert day["data"]["date"] == TODAY
    assert day["data"]["writable"] is True
    assert day["data"]["todos"] == []
    assert day["data"]["errands"] == []


def test_human_flag_writes_stderr_and_keeps_json(planner_home, run_cli):
    code, payload, err = run_cli(["--human", "context"])
    assert code == 0
    assert payload["ok"] is True
    assert payload["command"] == "context"
    assert "今天" in err
    assert "To Do" in err


def test_unknown_command_is_usage_json(planner_home, run_cli):
    code, payload, _ = run_cli(["not-a-command"])
    assert code == 2
    assert payload["ok"] is False
    assert payload["command"] is None
    assert payload["error"]["code"] == "UsageError"
    assert "today" not in payload
