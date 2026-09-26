def test_recurrence_cli_round_trip(planner_home, run_cli) -> None:
    code, created, _ = run_cli(
        [
            "recurrence",
            "add",
            "--kind",
            "errand",
            "--title",
            "吃药",
            "--frequency",
            "daily",
            "--start-date",
            "today",
            "--start",
            "08:00",
        ]
    )
    assert code == 0
    assert created["command"] == "recurrence.add"
    series_id = created["data"]["id"]

    code, listed, _ = run_cli(["recurrence", "list"])
    assert code == 0
    assert listed["data"]["items"][0]["id"] == series_id

    code, paused, _ = run_cli(["recurrence", "pause", series_id])
    assert code == 0
    assert paused["data"]["state"] == "paused"


def test_recurrence_cli_delete_requires_stopped(planner_home, run_cli) -> None:
    code, created, _ = run_cli(
        [
            "recurrence",
            "add",
            "--kind",
            "errand",
            "--title",
            "吃药",
            "--frequency",
            "daily",
            "--start-date",
            "today",
        ]
    )
    assert code == 0
    series_id = created["data"]["id"]
    code, conflict, _ = run_cli(["recurrence", "delete", series_id])
    assert code == 1
    assert conflict["error"]["code"] == "Conflict"
    assert run_cli(["recurrence", "stop", series_id])[0] == 0
    code, deleted, _ = run_cli(["recurrence", "delete", series_id])
    assert code == 0
    assert deleted["data"] == {"ok": True}
    assert run_cli(["recurrence", "list"])[1]["data"]["items"] == []
