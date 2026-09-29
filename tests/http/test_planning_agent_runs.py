"""Planning agents return drafts and never write the live planner database."""

from __future__ import annotations

import json
import shlex
import sys
import time


def _wait(client, run_id: str) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        run = client.get(f"/api/agent-runs/{run_id}").json()
        if run["result"] is not None:
            return run
        time.sleep(0.02)
    raise AssertionError("planning agent did not finish")


def test_planning_run_isolated_and_updates_only_draft(client, tmp_path) -> None:
    draft = client.post(
        "/api/planning/drafts",
        json={"requestId": "draft-1", "recoveryGeneration": None},
    ).json()
    script = tmp_path / "planning-agent.py"
    script.write_text(
        '''import json, os, subprocess, sys
from pathlib import Path
# A mistaken normal CLI write must target the disposable root supplied by the
# planning runner, not the TestClient application's SQLite file.
subprocess.run([sys.executable, "-m", "local_planner", "inventory", "add", "--title", "must stay isolated"], check=True)
Path(os.environ["LOCAL_PLANNER_PLAN_RESULT_FILE"]).write_text(json.dumps({"document": {"goals": []}, "message": "草案已生成"}))
''',
        encoding="utf-8",
    )
    launcher = client.post(
        "/api/launchers",
        json={"name": "planning stub", "command": shlex.join([sys.executable, str(script)])},
    ).json()
    response = client.post(
        "/api/agent-runs",
        json={
            "launcherId": launcher["id"], "requestId": "run-1", "prompt": "帮我规划",
            "surface": "goals", "mode": "planning", "draftId": draft["id"],
            "expectedDraftRevision": draft["revision"], "recoveryGeneration": None,
        },
    )
    assert response.status_code == 202, response.text
    finished = _wait(client, response.json()["id"])
    assert finished["status"] == "succeeded"
    assert finished["result"]["draft"]["runStatus"] == "succeeded"
    assert finished["result"]["draft"]["conversation"][-1]["content"] == "草案没有变化，正式规划未改动。"
    assert finished["result"]["message"] == "草案没有变化，正式规划未改动。"


def test_planning_run_reports_stale_draft_revision_without_starting_launcher(client, tmp_path) -> None:
    draft = client.post(
        "/api/planning/drafts",
        json={"requestId": "draft-stale", "recoveryGeneration": None},
    ).json()
    changed = client.post(
        f"/api/planning/drafts/{draft['id']}/actions",
        json={"operation": "update", "expectedRevision": draft["revision"], "recoveryGeneration": None,
              "requestId": "draft-stale-change", "document": {"goals": []}},
    ).json()
    sentinel = tmp_path / "should-not-run"
    launcher = client.post(
        "/api/launchers",
        json={"name": "must not run", "command": shlex.join([sys.executable, "-c", f"from pathlib import Path; Path({str(sentinel)!r}).write_text('ran')"])},
    ).json()
    response = client.post(
        "/api/agent-runs",
        json={
            "launcherId": launcher["id"], "requestId": "run-stale", "prompt": "继续调整",
            "surface": "goals", "mode": "planning", "draftId": draft["id"],
            "expectedDraftRevision": draft["revision"], "recoveryGeneration": None,
        },
    )
    assert response.status_code == 202, response.text
    finished = _wait(client, response.json()["id"])
    assert finished["status"] == "failed"
    assert finished["result"]["message"] == "草案已发生变化，请刷新后重试"
    assert finished["result"]["draft"]["revision"] == changed["revision"]
    assert not sentinel.exists()


def test_draft_apply_persists_candidate_without_creating_a_task(client) -> None:
    draft = client.post(
        "/api/planning/drafts",
        json={"requestId": "manual-draft", "recoveryGeneration": None},
    ).json()
    document = {"goals": [{
        "id": "roadmap-csp", "title": "通过 CSP", "notes": "", "horizonText": "明年",
        "parentGoalId": None, "state": "active", "endReason": None,
        "nextTaskId": None, "nextActionId": "candidate-1", "focusPhaseId": "phase-1",
        "phases": [{"id": "phase-1", "goalId": "roadmap-csp", "title": "基础", "notes": "",
                    "position": 0, "status": "open", "outcome": "完成两套模拟题", "horizonText": "本月"}],
        "actions": [{"id": "candidate-1", "goalId": "roadmap-csp", "phaseId": "phase-1",
                     "title": "做第一套模拟题", "notes": "", "position": 0, "taskId": None,
                     "scheduledDate": None, "completed": False, "discarded": False}],
    }]}
    updated = client.post(
        f"/api/planning/drafts/{draft['id']}/actions",
        json={"operation": "update", "expectedRevision": draft["revision"], "recoveryGeneration": None,
              "requestId": "manual-update", "document": document},
    )
    assert updated.status_code == 200, updated.text
    saved = client.post(
        f"/api/planning/drafts/{draft['id']}/actions",
        json={"operation": "apply", "expectedRevision": updated.json()["revision"], "recoveryGeneration": None,
              "requestId": "manual-apply"},
    )
    assert saved.status_code == 200, saved.text
    goal = client.get("/api/goals/roadmap-csp").json()
    assert goal["actions"][0]["taskId"] is None
    assert goal["tasks"] == []
    assert client.get("/api/inventory").json()["items"] == []


def test_global_draft_phase_selection_is_sent_to_planning_agent(client, tmp_path):
    draft = client.post("/api/planning/drafts", json={"requestId": "global-phase", "recoveryGeneration": None}).json()
    updated = client.post(f"/api/planning/drafts/{draft['id']}/actions", json={
        "operation": "update", "expectedRevision": draft["revision"], "recoveryGeneration": None, "requestId": "global-phase-update",
        "document": {"goals": [{"id": "new-goal", "title": "尚未保存", "phases": [{"id": "selected-phase", "title": "这一阶段"}]}]}}).json()
    script = tmp_path / "phase-agent.py"
    script.write_text("import json,os\nfrom pathlib import Path\nc=json.loads(Path(os.environ['LOCAL_PLANNER_CONTEXT_FILE']).read_text())\nassert c['selectedPhaseId']=='selected-phase'\nPath(os.environ['LOCAL_PLANNER_PLAN_RESULT_FILE']).write_text(json.dumps({'document':c['document'],'message':'已保留选中阶段'}))")
    launcher=client.post("/api/launchers",json={"name":"phase-agent","command":shlex.join([sys.executable,str(script)])}).json()
    response=client.post("/api/agent-runs",json={"launcherId":launcher["id"],"requestId":"global-phase-run","prompt":"调整这一阶段",
        "surface":"goals","mode":"planning","draftId":draft["id"],"expectedDraftRevision":updated["revision"],
        "selectedPhaseId":"selected-phase","recoveryGeneration":None})
    assert response.status_code==202,response.text
    assert _wait(client,response.json()["id"])["status"]=="succeeded"


def test_agent_cannot_resurrect_archived_goal_and_reports_actual_rejection(client, tmp_path):
    # A model can remember an old ID from conversation even when it is omitted
    # from editable context. The host must reject it without a false success.
    draft = client.post('/api/planning/drafts', json={'requestId': 'seed-archived', 'recoveryGeneration': None}).json()
    def change(d, operation, **kw):
        response = client.post(f"/api/planning/drafts/{d['id']}/actions", json={
            'operation': operation, 'expectedRevision': d['revision'], 'recoveryGeneration': None,
            'requestId': f"{d['id']}-{d['revision']}-{operation}", **kw})
        assert response.status_code == 200, response.text
        return response.json()
    change(change(draft, 'update', document={'goals': [{'id': 'old-goal', 'title': '原规划'}]}), 'apply')
    draft = client.post('/api/planning/drafts', json={'requestId': 'remove-archived', 'recoveryGeneration': None}).json()
    change(change(draft, 'update', document={'goals': []}), 'apply')
    draft = client.post('/api/planning/drafts', json={'requestId': 'new-after-archive', 'recoveryGeneration': None}).json()
    old_goal = client.get('/api/goals/old-goal').json()
    script = tmp_path / 'bad-reuse.py'
    script.write_text("import json,os\nfrom pathlib import Path\nc=json.loads(Path(os.environ['LOCAL_PLANNER_CONTEXT_FILE']).read_text())\nassert c['document']['goals']==[]\nPath(os.environ['LOCAL_PLANNER_PLAN_RESULT_FILE']).write_text(json.dumps({'document':{'goals':[{'id':'old-goal','title':'原规划','state':'active'}]},'message':'已经恢复成功'}))")
    launcher = client.post('/api/launchers', json={'name': 'bad reuse', 'command': shlex.join([sys.executable, str(script)])}).json()
    response = client.post('/api/agent-runs', json={
        'launcherId': launcher['id'], 'requestId': 'bad-reuse-run', 'prompt': '重新规划',
        'surface': 'goals', 'mode': 'planning', 'draftId': draft['id'],
        'expectedDraftRevision': draft['revision'], 'recoveryGeneration': None})
    assert response.status_code == 202
    finished = _wait(client, response.json()['id'])
    assert finished['status'] == 'failed'
    assert '尝试复用已删除或已结束的目标' in finished['result']['message']
    assert '本次未更改草案或正式规划' in finished['result']['message']
    assert '已经恢复成功' not in finished['result']['message']
    assert finished['result']['draft']['document'] == draft['document']
    assert client.get('/api/goals/old-goal').json() == old_goal
