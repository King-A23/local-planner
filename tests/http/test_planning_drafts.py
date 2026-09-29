"""Real SQLite integration: preview/save cannot become implicit task scheduling."""
import copy
import uuid

from local_planner.domain import planning
from local_planner.http.app import create_app
from fastapi.testclient import TestClient


def create(client, **kwargs):
    r = client.post("/api/planning/drafts", json={"requestId": str(uuid.uuid4()), "recoveryGeneration": None, **kwargs})
    assert r.status_code == 200, r.text
    return r.json()


def action(client, draft, operation, **kwargs):
    r = client.post(f"/api/planning/drafts/{draft['id']}/actions", json={
        "operation": operation, "expectedRevision": draft["revision"],
        "recoveryGeneration": draft["recoveryGeneration"], "requestId": str(uuid.uuid4()), **kwargs})
    assert r.status_code == 200, r.text
    return r.json()


def document():
    return {"goals": [
        {"id": "csp", "title": "通过 CSP", "horizonText": "明年", "phases": [
            {"id": "foundation", "title": "补齐基础", "outcome": "独立完成基础题", "horizonText": "近期"},
            {"id": "simulation", "title": "模拟训练", "outcome": "稳定达到目标分数"}],
         "focusPhaseId": "foundation", "nextActionId": "first-action", "actions": [
             {"id": "first-action", "phaseId": "foundation", "title": "完成第一套练习"},
             {"id": "later-action", "phaseId": "simulation", "title": "一次限时模拟"}]},
        {"id": "algorithms", "title": "掌握基础算法", "horizonText": "本月", "parentGoalId": "csp"},
    ]}


def saved(client):
    draft = action(client, create(client), "update", document=document())
    return action(client, draft, "apply")


def test_draft_preview_save_and_materialize_preserve_single_task(client, uow):
    draft = create(client)
    updated = action(client, draft, "update", document=document())
    assert client.get("/api/goals").json()["items"] == []
    assert uow.list_inventory_tasks() == []
    assert updated["canUndo"]
    assert {c["type"] for c in updated["changes"]} == {"added"}
    applied = action(client, updated, "apply")
    assert applied["canRevert"]
    goals = client.get("/api/goals").json()["items"]
    assert len(goals) == 2
    assert uow.list_inventory_tasks() == []
    assert uow.get_goal("algorithms").parent_goal_id == "csp"
    goal = client.get("/api/goals/csp").json()
    request = {"operation": "materialize-action", "actionId": "first-action", "destination": "today",
               "requestId": "materialize-first", "expectedRevision": goal["revision"], "recoveryGeneration": None}
    r = client.post("/api/goals/csp/actions", json=request)
    assert r.status_code == 200, r.text
    made = r.json()
    tid = made["actions"][0]["taskId"]
    assert made["nextTaskId"] == tid and made["nextActionId"] is None
    assert uow.get_task(tid).current_scheduled_date == made["serverToday"]
    assert client.post("/api/goals/csp/actions", json=request).status_code == 200
    assert len(uow.list_goal_tasks("csp")) == 1
    blocked = client.post(f"/api/planning/drafts/{applied['id']}/actions", json={
        "operation": "revert", "expectedRevision": applied["revision"], "recoveryGeneration": None, "requestId": "undo-after-materialize"})
    assert blocked.status_code == 409
    assert uow.get_task(tid).current_scheduled_date == made["serverToday"]


def test_persistent_draft_conversation_question_failure_stop_and_restart(client, uow, clock, tmp_path):
    draft = create(client)
    with uow.transaction():
        running = planning.begin_draft_run(clock, uow, draft["id"], expected_revision=draft["revision"],
                                          recovery_generation=None, prompt="帮我安排明年考试", request_id="run-1")
        asked = planning.finish_draft_run(clock, uow, draft["id"], request_id="run-1", recovery_generation=None,
                                         question="希望达到什么分数？")
    assert asked["document"] == draft["document"]
    assert [m["role"] for m in asked["conversation"]] == ["user", "assistant"]
    with uow.transaction():
        planning.begin_draft_run(clock, uow, draft["id"], expected_revision=asked["revision"],
                                 recovery_generation=None, prompt="200分", request_id="run-2")
        generated = planning.finish_draft_run(clock, uow, draft["id"], request_id="run-2", recovery_generation=None,
                                             document=document(), message="先练基础，再做模拟。")
    with uow.transaction():
        planning.begin_draft_run(clock, uow, draft["id"], expected_revision=generated["revision"],
                                 recovery_generation=None, prompt="再调整", request_id="run-3")
        stopped = planning.finish_draft_run(clock, uow, draft["id"], request_id="run-3", recovery_generation=None, stopped=True)
    assert stopped["document"] == generated["document"]
    with uow.transaction():
        planning.begin_draft_run(clock, uow, draft["id"], expected_revision=stopped["revision"],
                                 recovery_generation=None, prompt="继续调整", request_id="run-4")
    # App restart retains both the conversation and latest valid structured plan.
    restarted = create_app(clock=clock, uow=uow, data_dir=tmp_path)
    with TestClient(restarted, base_url="http://127.0.0.1:8787") as second:
        got = second.get(f"/api/planning/drafts/{draft['id']}").json()
    assert got["runStatus"] == "interrupted"
    assert got["document"] == generated["document"]
    assert got["conversation"][-1]["content"] == "继续调整"


def test_draft_undo_and_saved_revert_do_not_rewind_tasks(client, uow):
    applied = saved(client)
    draft = create(client, goalId="csp")
    edited = copy.deepcopy(draft["document"])
    edited["goals"][0]["phases"][0]["outcome"] = "掌握数组和排序"
    changed = action(client, draft, "update", document=edited)
    undone = action(client, changed, "undo")
    assert undone["document"] == draft["document"]
    changed = action(client, undone, "update", document=edited)
    edited_saved = action(client, changed, "apply")
    assert uow.get_phase("foundation").outcome == "掌握数组和排序"
    action(client, edited_saved, "revert")
    assert uow.get_phase("foundation").outcome == "独立完成基础题"
    assert uow.list_inventory_tasks() == []
    # A newer save prevented reverting the original apply.
    r = client.post(f"/api/planning/drafts/{applied['id']}/actions", json={
        "operation": "revert", "expectedRevision": applied["revision"], "recoveryGeneration": None, "requestId": "old-revert"})
    assert r.status_code == 409


def test_apply_is_idempotent_and_stale_goal_or_recovery_keeps_draft(client, uow):
    draft = action(client, create(client), "update", document=document())
    request = {"operation": "apply", "expectedRevision": draft["revision"], "recoveryGeneration": None, "requestId": "save-once"}
    url = f"/api/planning/drafts/{draft['id']}/actions"
    assert client.post(url, json=request).status_code == 200
    assert client.post(url, json=request).status_code == 200
    assert len(uow.list_goals()) == 2
    draft = create(client, goalId="csp")
    goal = uow.get_goal("csp")
    from dataclasses import replace
    uow.save_goal(replace(goal, revision=goal.revision + 1))
    r = client.post(f"/api/planning/drafts/{draft['id']}/actions", json={
        **request, "requestId": "stale-save", "expectedRevision": draft["revision"]})
    assert r.status_code == 409
    assert planning.get_draft(uow, draft["id"])["status"] == "editing"
    uow.meta.set("recovery_generation", "restored")
    r = client.post(f"/api/planning/drafts/{draft['id']}/actions", json={
        **request, "requestId": "restored-save", "expectedRevision": draft["revision"], "recoveryGeneration": "restored"})
    assert r.status_code == 409


def test_invalid_relationship_and_task_mutations_are_rejected_without_partial_write(client, uow):
    draft = create(client)
    bad = document()
    bad["goals"][0]["parentGoalId"] = "algorithms"
    url = f"/api/planning/drafts/{draft['id']}/actions"
    r = client.post(url, json={"operation": "update", "expectedRevision": draft["revision"], "recoveryGeneration": None,
                              "requestId": "cycle", "document": bad})
    assert r.status_code == 400
    assert planning.get_draft(uow, draft["id"])["document"] == {"goals": []}
    saved(client)
    g = uow.get_goal("csp")
    r = client.post("/api/goals/csp/actions", json={"operation": "materialize-action", "actionId": "first-action", "destination": "inventory",
                    "expectedRevision": g.revision, "recoveryGeneration": None, "requestId": "formal"})
    assert r.status_code == 200, r.text
    draft = create(client, goalId="csp")
    for field, value in [("completed", True), ("scheduledDate", "2026-08-30"), ("title", "偷偷改名"), ("taskId", None)]:
        bad = copy.deepcopy(draft["document"])
        bad["goals"][0]["actions"][0][field] = value
        r = client.post(f"/api/planning/drafts/{draft['id']}/actions", json={
            "operation": "update", "expectedRevision": draft["revision"], "recoveryGeneration": None,
            "requestId": f"invalid-{field}", "document": bad})
        assert r.status_code == 400, r.text
    assert uow.list_inventory_tasks()[0].title == "完成第一套练习"


def test_candidate_removal_and_phase_removal_keep_formal_task_boundaries(client, uow):
    saved(client)
    draft = create(client, goalId="csp")
    edited = copy.deepcopy(draft["document"])
    edited["goals"][0]["actions"] = [edited["goals"][0]["actions"][0]]
    edited["goals"][0]["phases"] = [edited["goals"][0]["phases"][0]]
    result = action(client, action(client, draft, "update", document=edited), "apply")
    assert uow.get_phase("simulation") is None
    assert uow.get_goal_action("later-action") is None
    action(client, result, "revert")
    assert uow.get_phase("simulation") is not None
    assert uow.get_goal_action("later-action") is not None


def test_revert_checks_new_relationships_outside_the_original_edit(client, uow):
    saved(client)
    other = client.post("/api/goals", json={"title": "独立方向", "requestId": "other", "recoveryGeneration": None}).json()
    draft = create(client, goalId="algorithms")
    edited = copy.deepcopy(draft["document"])
    edited["goals"][0]["parentGoalId"] = other["id"]
    applied = action(client, action(client, draft, "update", document=edited), "apply")
    goal = uow.get_goal("csp")
    r = client.post("/api/goals/csp/actions", json={"operation": "set-parent", "parentGoalId": "algorithms",
                    "expectedRevision": goal.revision, "recoveryGeneration": None})
    assert r.status_code == 200
    r = client.post(f"/api/planning/drafts/{draft['id']}/actions", json={
        "operation": "revert", "expectedRevision": applied["revision"], "recoveryGeneration": None, "requestId": "cycle-revert"})
    assert r.status_code == 409
    assert uow.get_goal("algorithms").parent_goal_id == other["id"]


def test_completed_phase_is_not_rewritten_by_agent_and_manual_action_can_be_removed(client, uow):
    saved(client)
    goal = client.get("/api/goals/csp").json()
    r = client.post("/api/goals/csp/actions", json={"operation": "edit-phase", "phaseId": "foundation",
                    "title": "补齐基础", "notes": "", "outcome": "独立完成基础题", "horizonText": "近期", "status": "done",
                    "expectedRevision": goal["revision"], "recoveryGeneration": None})
    assert r.status_code == 200
    draft = create(client, goalId="csp")
    edited = copy.deepcopy(draft["document"])
    edited["goals"][0]["phases"][0]["outcome"] = "覆盖完成记录"
    r = client.post(f"/api/planning/drafts/{draft['id']}/actions", json={
        "operation": "update", "expectedRevision": draft["revision"], "recoveryGeneration": None,
        "requestId": "completed-edit", "document": edited})
    assert r.status_code == 400
    assert uow.get_phase("foundation").outcome == "独立完成基础题"
    goal = uow.get_goal("algorithms")
    r = client.post("/api/goals/algorithms/actions", json={"operation": "add-action", "title": "待移除的候选行动",
                    "requestId": "candidate-via-api", "expectedRevision": goal.revision, "recoveryGeneration": None})
    assert r.status_code == 200
    aid = r.json()["actions"][0]["id"]
    draft = create(client, goalId="algorithms")
    edited = copy.deepcopy(draft["document"])
    edited["goals"][0]["actions"] = []
    action(client, action(client, draft, "update", document=edited), "apply")
    assert uow.get_goal_action(aid) is None


def test_only_latest_planning_save_can_be_reverted(client):
    first = saved(client)
    draft = create(client, goalId='csp')
    doc = copy.deepcopy(draft['document'])
    doc['goals'][0]['notes'] = 'Later save'
    second = action(client, action(client, draft, 'update', document=doc), 'apply')
    assert second['canRevert']
    assert not client.get('/api/planning/drafts/' + first['id']).json()['canRevert']
    rejected = client.post('/api/planning/drafts/' + first['id'] + '/actions', json={
        'operation': 'revert', 'expectedRevision': first['revision'],
        'recoveryGeneration': None, 'requestId': 'revert-old'})
    assert rejected.status_code == 409
    action(client, second, 'revert')
    assert client.get('/api/goals/csp').json()['notes'] == ''
