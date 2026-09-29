"""Goal HTTP contract uses only the fixture SQLite database."""

from __future__ import annotations

from dataclasses import replace


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


def test_permanent_goal_delete_keeps_tasks_and_detaches_children(client, uow) -> None:
    goal = _create(client, "delete-create")
    phase_goal = _action(client, goal, "add-phase", title="基础", notes="", requestId="delete-phase")
    phase_id = phase_goal["phases"][0]["id"]
    linked = _action(client, phase_goal, "add-task", title="练习", notes="", phaseId=phase_id,
                     requestId="delete-task")
    task_id = linked["tasks"][0]["taskId"]
    selected = _action(client, linked, "next", taskId=task_id)
    scheduled = _action(client, selected, "schedule-next", expectedTaskId=task_id,
                        expectedScheduledDate=None)
    child = client.post("/api/goals", json={"title": "子规划", "requestId": "child-create",
                                             "recoveryGeneration": None}).json()
    child = _action(client, child, "set-parent", parentGoalId=goal["id"])
    draft = client.post("/api/planning/drafts", json={"goalId": goal["id"],
        "requestId": "delete-draft", "recoveryGeneration": None}).json()
    assert draft["id"]
    preview = client.get(f"/api/goals/{goal['id']}/deletion-preview")
    assert preview.status_code == 200
    assert preview.json()["retainedTaskCount"] == 1
    assert preview.json()["detachedChildCount"] == 1
    assert preview.json()["removedDraftCount"] == 1
    url = f"/api/goals/{goal['id']}/delete"
    body = {"expectedRevision": scheduled["revision"], "recoveryGeneration": None,
            "confirmTitle": goal["title"]}
    assert client.post(url, json={**body, "confirmTitle": "wrong"}).status_code == 400
    assert client.post(url, json={**body, "expectedRevision": 1}).status_code == 409
    response = client.post(url, json=body)
    assert response.status_code == 200, response.text
    assert response.json()["deleted"] is True
    assert client.get(f"/api/goals/{goal['id']}").status_code == 404
    assert client.get(f"/api/planning/drafts/{draft['id']}").status_code == 404
    assert uow.get_goal(child["id"]).parent_goal_id is None
    task = uow.get_task(task_id)
    assert task.goal_id is None and task.phase_id is None
    assert task.current_scheduled_date == scheduled["serverToday"]
    entry = uow.get_entry(scheduled["serverToday"], task_id)
    assert entry is not None and entry.goal_id_snapshot is None
    assert uow.list_goal_actions(goal["id"]) == []
    assert uow.list_phases(goal["id"]) == []
    assert client.post("/api/goals", json={"title": goal["title"], "notes": goal["notes"],
        "horizonText": goal["horizonText"], "requestId": "delete-create",
        "recoveryGeneration": None}).status_code == 409


def test_permanent_goal_delete_unlinks_discarded_task_and_rejects_running_draft(client, uow) -> None:
    goal = _create(client)
    linked = _action(client, goal, "add-task", title="旧任务", notes="", requestId="old-task")
    task_id = linked["tasks"][0]["taskId"]
    uow.save_task(replace(uow.get_task(task_id), discarded_at="2026-08-29T00:00:00Z"))
    draft = client.post("/api/planning/drafts", json={"goalId": goal["id"],
        "requestId": "running-draft", "recoveryGeneration": None}).json()
    raw = uow.planning.get(draft["id"])
    raw["runStatus"] = "running"
    uow.planning.save(raw)
    body = {"expectedRevision": linked["revision"], "recoveryGeneration": None,
            "confirmTitle": goal["title"]}
    assert client.post(f"/api/goals/{goal['id']}/delete", json=body).status_code == 409
    assert uow.get_goal(goal["id"]) is not None
    raw["runStatus"] = "stopped"
    uow.planning.save(raw)
    assert client.post(f"/api/goals/{goal['id']}/delete", json=body).status_code == 200
    assert uow.get_task(task_id).discarded_at is not None
    assert uow.get_task(task_id).goal_id is None


def test_permanent_goal_delete_preserves_sealed_day_snapshot(client, uow) -> None:
    goal = _create(client)
    linked = _action(client, goal, "add-task", title="已完成练习", notes="", requestId="sealed-task")
    task_id = linked["tasks"][0]["taskId"]
    selected = _action(client, linked, "next", taskId=task_id)
    scheduled = _action(client, selected, "schedule-next", expectedTaskId=task_id,
                        expectedScheduledDate=None)
    day = scheduled["serverToday"]
    uow.conn.execute("UPDATE days SET status='sealed', sealed_at='2026-08-31T00:00:00Z' WHERE date=?", (day,))
    body = {"expectedRevision": scheduled["revision"], "recoveryGeneration": None,
            "confirmTitle": goal["title"]}
    response = client.post(f"/api/goals/{goal['id']}/delete", json=body)
    assert response.status_code == 200, response.text
    assert uow.get_task(task_id).goal_id is None
    assert uow.get_entry(day, task_id).goal_title_snapshot == goal["title"]


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


def test_roadmap_action_contract_keeps_candidate_out_of_todos_until_materialized(client) -> None:
    parent = _create(client, "parent")
    goal = _create(client, "child")
    goal = _action(client, goal, "set-parent", parentGoalId=parent["id"])
    assert goal["parentGoalId"] == parent["id"]

    goal = _action(
        client, goal, "add-phase", title="准备", notes="", outcome="完成两套模拟题",
        horizonText="本月", requestId="phase-roadmap",
    )
    phase = goal["phases"][0]
    assert phase["outcome"] == "完成两套模拟题"
    action_goal = _action(
        client, goal, "add-action", title="做第一套模拟题", notes="记录错题",
        phaseId=phase["id"], requestId="candidate-1",
    )
    candidate = action_goal["actions"][0]
    assert candidate["taskId"] is None
    assert action_goal["tasks"] == []

    action_goal = _action(client, action_goal, "next-action", actionId=candidate["id"])
    materialized = _action(
        client, action_goal, "materialize-action", actionId=candidate["id"],
        destination="today", requestId="materialize-1",
    )
    linked = materialized["actions"][0]
    assert linked["taskId"] is not None
    assert linked["scheduledDate"] == materialized["serverToday"]
    assert materialized["nextTaskId"] == linked["taskId"]
    assert materialized["nextActionId"] is None


def test_removing_selected_candidate_keeps_request_tombstone_without_fk_failure(client) -> None:
    goal = _create(client, "remove-action-goal")
    goal = _action(client, goal, "add-action", title="可撤销行动", notes="", phaseId=None, requestId="remove-candidate")
    action_id = goal["actions"][0]["id"]
    goal = _action(client, goal, "next-action", actionId=action_id)
    removed = _action(client, goal, "remove-action", actionId=action_id)
    assert removed["actions"] == []
    assert removed["nextActionId"] is None
