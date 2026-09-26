from __future__ import annotations

import shlex

import pytest

from local_planner.launchers import compose_prompt

TODAY = "2026-08-31"


@pytest.mark.parametrize(
    ("user_text", "collection", "start", "end"),
    [
        ("今天九点开始写设计", "todos", "09:00", None),
        ("今天下午三点前取快递", "errands", None, "15:00"),
        ("今天九点到十点写设计", "todos", "09:00", "10:00"),
        ("今天写设计（没说时间）", "todos", None, None),
    ],
)
def test_agent_time_examples_persist_independent_clocks(
    planner_home, run_cli, user_text, collection, start, end
):
    prompt = compose_prompt(user_text)
    prefix = f"- {user_text}："
    command = next(line.removeprefix(prefix) for line in prompt.splitlines() if line.startswith(prefix))
    code, payload, _ = run_cli(shlex.split(command)[3:])
    assert code == 0, payload
    row = payload["data"][collection][0]
    assert (row["startClock"], row["endClock"]) == (start, end)
    code, persisted, _ = run_cli(["day", "open", "today"])
    assert code == 0
    row = persisted["data"][collection][0]
    assert (row["startClock"], row["endClock"]) == (start, end)


@pytest.mark.parametrize("kind", ["todo", "errand"])
@pytest.mark.parametrize(
    ("flags", "expected"),
    [([], (None, None)), (["--start", "09:00"], ("09:00", None)),
     (["--end", "10:00"], (None, "10:00"))],
)
def test_add_clocks_are_optional_and_independent(planner_home, run_cli, kind, flags, expected):
    code, payload, _ = run_cli(["day", kind, "add", "today", "--title", "事项", *flags])
    assert code == 0, payload
    row = payload["data"]["todos" if kind == "todo" else "errands"][0]
    assert (row["startClock"], row["endClock"]) == expected


def test_cli_sets_target_date_and_clocks(planner_home, run_cli):
    code, inv, _ = run_cli(
        ["inventory", "add", "--title", "带目标日", "--target-date", "2026-09-03"]
    )
    assert code == 0
    assert inv["data"]["targetDate"] == "2026-09-03"
    assert "todos" not in inv["data"]

    listed = run_cli(["inventory", "list"])[1]
    assert listed["data"]["items"][0]["targetDate"] == "2026-09-03"
    today = run_cli(["day", "open", "today"])[1]
    assert today["data"]["todos"] == []

    code, today_target, _ = run_cli(
        ["inventory", "add", "--title", "今天相关", "--target-date", "today"]
    )
    assert code == 0
    assert today_target["data"]["targetDate"] == TODAY
    assert "todos" not in today_target["data"]

    plan = run_cli(
        [
            "day",
            "todo",
            "add",
            "today",
            "--title",
            "有钟",
            "--start",
            "09:00",
            "--end",
            "11:00",
        ]
    )[1]
    task_id = plan["data"]["todos"][0]["taskId"]
    assert plan["data"]["todos"][0]["startClock"] == "09:00"
    assert plan["data"]["todos"][0]["endClock"] == "11:00"

    errand = run_cli(
        ["day", "errand", "add", "today", "--title", "差事", "--start", "13:00"]
    )[1]
    assert errand["data"]["errands"][0]["startClock"] == "13:00"
    assert errand["data"]["errands"][0]["endClock"] is None

    only_start = run_cli(
        ["day", "todo", "time", TODAY, task_id, "--start", "08:00"]
    )[1]
    row = next(item for item in only_start["data"]["todos"] if item["taskId"] == task_id)
    assert row["startClock"] == "08:00"
    assert row["endClock"] == "11:00"

    cleared = run_cli(["day", "todo", "time", TODAY, task_id])[1]
    row = next(item for item in cleared["data"]["todos"] if item["taskId"] == task_id)
    assert row["startClock"] is None
    assert row["endClock"] is None
