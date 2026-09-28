from __future__ import annotations

TODAY = "2026-08-31"


def test_context_includes_today_inventory_and_scheduled_ahead(planner_home, run_cli):
    run_cli(["day", "todo", "add", "today", "--title", "今天的事"])
    run_cli(["inventory", "add", "--title", "还不定哪天"])
    ahead = run_cli(["inventory", "add", "--title", "周四答辩"])[1]
    task_id = ahead["data"]["taskId"]
    run_cli(["task", "schedule", task_id, "--date", "2026-09-03"])

    code, payload, _ = run_cli(["context"])
    assert code == 0
    data = payload["data"]
    assert data["today"] == TODAY
    assert data["writable"] is True
    assert {item["title"] for item in data["todos"]} == {"今天的事"}
    assert {item["title"] for item in data["inventory"]} == {"还不定哪天"}
    assert data["scheduledAhead"] == [
        {
            "taskId": task_id,
            "title": "周四答辩",
            "notes": "",
            "date": "2026-09-03",
            "goalId": None,
            "phaseId": None,
            "goalTitle": None,
            "phaseTitle": None,
        }
    ]
    assert "errands" in data
    assert data["inventoryCount"] == 1
