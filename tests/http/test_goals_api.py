"""Goal HTTP contract uses only the fixture SQLite database."""

from __future__ import annotations


def _create(client, request_id: str = "goal-create") -> dict:
    response = client.post(
        "/api/goals",
        json={
            "title": "通过 CSP",
            "notes": "先复习算法",
            "horizonText": "明年",
            "requestId": request_id,
            "recoveryGeneration": None,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _action(client, goal: dict, operation: str, **values: object) -> dict:
    response = client.post(
        f"/api/goals/{goal['id']}/actions",
        json={
            "operation": operation,
            "expectedRevision": goal["revision"],
            "recoveryGeneration": goal["recoveryGeneration"],
            **values,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_goal_routes_keep_full_action_contract_and_candidate_locations(client) -> None:
    created = _create(client)
    assert created["state"] == "active"
    assert created["phases"] == []
    assert client.get("/api/goals").json()["items"][0]["id"] == created["id"]

    phase = _action(
        client, created, "add-phase", title="基础", notes="刷题", requestId="phase-1"
    )
    phase_id = phase["phases"][0]["id"]
    task_goal = _action(
        client, phase, "add-task", title="完成第一套题", notes="", phaseId=phase_id,
        requestId="task-1",
    )
    task_id = task_goal["tasks"][0]["taskId"]
    candidates = client.get("/api/goals/candidates")
    assert candidates.status_code == 200
    assert candidates.json()["items"] == [
        {
            "taskId": task_id,
            "title": "完成第一套题",
            "notes": "",
            "goalId": created["id"],
            "phaseId": phase_id,
            "scheduledDate": None,
            "completed": False,
            "targetDate": None,
            "seriesId": None,
            "goalTitle": "通过 CSP",
        }
    ]
    selected = _action(client, task_goal, "next", taskId=task_id)
    scheduled = _action(
        client,
        selected,
        "schedule-next",
        expectedTaskId=task_id,
        expectedScheduledDate=None,
    )
    assert scheduled["tasks"][0]["scheduledDate"] == scheduled["serverToday"]


def test_goal_action_rejects_stale_recovery_and_requires_operation_fields(client, uow) -> None:
    created = _create(client)
    uow.meta.set("recovery_generation", "after-restore")
    stale = client.post(
        f"/api/goals/{created['id']}/actions",
        json={
            "operation": "edit", "expectedRevision": created["revision"],
            "recoveryGeneration": None, "title": "新标题", "notes": "", "horizonText": "",
        },
    )
    assert stale.status_code == 409

    fresh_but_missing = client.post(
        f"/api/goals/{created['id']}/actions",
        json={
            "operation": "edit", "expectedRevision": created["revision"],
            "recoveryGeneration": "after-restore", "title": "新标题", "notes": "",
        },
    )
    assert fresh_but_missing.status_code == 400

    stale_create = client.post(
        "/api/goals",
        json={
            "title": "旧页面新建", "requestId": "stale-create",
            "recoveryGeneration": None,
        },
    )
    assert stale_create.status_code == 409

    missing_nullable = client.post(
        f"/api/goals/{created['id']}/actions",
        json={
            "operation": "next", "expectedRevision": created["revision"],
            "recoveryGeneration": "after-restore",
        },
    )
    assert missing_nullable.status_code == 400


def test_goal_agent_surface_never_falls_back_to_today(client) -> None:
    missing = client.post(
        "/api/agent-runs",
        json={"launcherId": "unknown", "requestId": "agent-goal", "prompt": "整理", "surface": "goal"},
    )
    # Launcher validation precedes work, but goal page input is still rejected
    # as a request validation error before an Agent run can be created.
    assert missing.status_code == 400
