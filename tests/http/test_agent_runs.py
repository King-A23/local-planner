"""Exercise real launcher processes, suspension, stop, and request recovery."""
import os
import shlex
import sys
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from local_planner.runtime import interprocess_lock


def wait_for(fn, predicate=bool, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = fn()
        if predicate(value):
            return value
        time.sleep(0.02)
    raise AssertionError("condition did not become true")


def launcher(client, tmp_path, source):
    script = tmp_path / f"stub-{uuid.uuid4()}.py"
    script.write_text(source)
    res = client.post('/api/launchers', json={
        'name': 'Controlled stub', 'command': shlex.join([sys.executable, str(script)])
    })
    assert res.status_code == 200
    return res.json()['id']


def start(client, lid, **overrides):
    body = dict(launcherId=lid, requestId=str(uuid.uuid4()), prompt='test control') | overrides
    res = client.post('/api/agent-runs', json=body)
    assert res.status_code == 202, res.text
    return res.json(), body


def finished(client, rid):
    return wait_for(lambda: client.get(f'/api/agent-runs/{rid}').json(), lambda r: r['result'] is not None)


def test_pause_resume_freezes_descendant_and_keeps_database_available(client, tmp_path):
    progress = tmp_path / 'ticks'
    child = f'import time; from pathlib import Path; p=Path({str(progress)!r});\nfor i in range(200): p.write_text(str(i)); time.sleep(.03)'
    lid = launcher(client, tmp_path, f'import subprocess,sys\np=subprocess.Popen([sys.executable,"-c",{child!r}]); p.wait()')
    run, body = start(client, lid)
    wait_for(progress.exists)
    paused = client.post(f'/api/agent-runs/{run["id"]}/pause', json={})
    assert paused.status_code == 200
    assert paused.json()['status'] == 'paused'
    time.sleep(.06)
    tick = progress.read_text()
    elapsed = paused.json()['elapsedSeconds']
    time.sleep(.15)
    assert progress.read_text() == tick
    assert client.get('/api/agent-runs').json()['run']['status'] == 'paused'
    assert client.get('/api/agent-runs').json()['run']['elapsedSeconds'] == elapsed
    # Pausing must not strand the database lock.
    assert client.post('/api/inventory/tasks', json={'title': 'while paused'}).status_code == 200
    resumed = client.post(f'/api/agent-runs/{run["id"]}/resume', json={})
    assert resumed.json()['status'] == 'running'
    wait_for(progress.read_text, lambda value: value != tick)
    client.post(f'/api/agent-runs/{run["id"]}/stop', json={})
    result = finished(client, run['id'])
    assert result['status'] == 'stopped_with_changes'
    assert result['result']['ok'] is False


def test_pause_time_does_not_consume_timeout(client, tmp_path, monkeypatch):
    import local_planner.http.app as app_module
    original = app_module.run_launcher
    def short_run(*args, **kwargs):
        kwargs['timeout'] = .9
        return original(*args, **kwargs)
    monkeypatch.setattr(app_module, 'run_launcher', short_run)
    ready = tmp_path / 'ready'
    lid = launcher(client, tmp_path, f'from pathlib import Path\nimport time\nPath({str(ready)!r}).touch()\ntime.sleep(.45)\nprint("done")')
    run, _ = start(client, lid)
    wait_for(ready.exists)
    assert client.post(f'/api/agent-runs/{run["id"]}/pause', json={}).status_code == 200
    time.sleep(1.1)
    assert client.get('/api/agent-runs').json()['run']['status'] == 'paused'
    client.post(f'/api/agent-runs/{run["id"]}/resume', json={})
    result = finished(client, run['id'])
    assert result['status'] == 'succeeded'
    assert result['result']['stdout'].strip() == 'done'


def test_request_deduplication_and_single_active_run(client, tmp_path):
    lid = launcher(client, tmp_path, 'import time; time.sleep(30)')
    run, body = start(client, lid)
    again = client.post('/api/agent-runs', json=body)
    assert again.json()['id'] == run['id']
    assert client.post('/api/agent-runs', json=body | {'requestId': 'different'}).status_code == 409
    assert client.post('/api/agent-runs', json=body | {'prompt': 'different'}).status_code == 409
    client.post(f'/api/agent-runs/{run["id"]}/stop', json={})
    finished(client, run['id'])
    assert client.post('/api/agent-runs', json=body).json()['id'] == run['id']


def test_pause_does_not_suspend_while_database_is_locked(client, tmp_path):
    ready = tmp_path / 'ready'
    lid = launcher(client, tmp_path, f'from pathlib import Path\nimport time\nPath({str(ready)!r}).touch()\ntime.sleep(30)')
    run, _ = start(client, lid)
    wait_for(ready.exists)
    with interprocess_lock(tmp_path):
        response = client.post(f'/api/agent-runs/{run["id"]}/pause', json={})
    assert response.status_code == 409
    assert client.get('/api/agent-runs').json()['run']['status'] == 'running'
    client.post(f'/api/agent-runs/{run["id"]}/stop', json={})
    finished(client, run['id'])


def test_stop_keeps_partial_changes_and_new_prompt_reads_fresh_context(client, tmp_path, monkeypatch):
    monkeypatch.setenv('LOCAL_PLANNER_CLOCK', '2026-08-30T12:00:00+08:00')
    monkeypatch.setenv('LOCAL_PLANNER_ALLOW_CLOCK_OVERRIDE', '1')
    proof = tmp_path / 'proof'
    pidfile = tmp_path / 'child-pid'
    lid = launcher(client, tmp_path, f'''import subprocess,sys,time,json,os
from pathlib import Path
subprocess.run([sys.executable,"-m","local_planner","inventory","add","--title","already saved"],check=True)
p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"])
Path({str(pidfile)!r}).write_text(str(p.pid))
time.sleep(60)
''')
    run, _ = start(client, lid)
    wait_for(pidfile.exists)
    client.post(f'/api/agent-runs/{run["id"]}/pause', json={})
    client.post(f'/api/agent-runs/{run["id"]}/stop', json={})
    old = finished(client, run['id'])
    assert old['status'] == 'stopped_with_changes'
    assert old['result']['receipt']['counts'] == {'todo_added': 1}
    pid = int(pidfile.read_text())
    def gone():
        try: os.kill(pid, 0)
        except ProcessLookupError: return True
        return False
    wait_for(gone)
    new_lid = launcher(client, tmp_path, f'''import os,json
from pathlib import Path
context=json.loads(Path(os.environ["LOCAL_PLANNER_CONTEXT_FILE"]).read_text())
assert any(item["title"]=="already saved" for item in context["inventory"])
assert os.environ["LOCAL_PLANNER_PROMPT"].endswith("adjusted prompt")
Path({str(proof)!r}).touch()
''')
    new, _ = start(client, new_lid, prompt='adjusted prompt')
    assert finished(client, new['id'])['result']['ok'] is True
    assert proof.exists()
    assert len(client.get('/api/inventory').json()['items']) == 1


def test_shutdown_cleans_paused_run(app, tmp_path):
    pidfile = tmp_path / 'pid'
    with TestClient(app, base_url='http://127.0.0.1:8787') as client:
        lid = launcher(client, tmp_path, f'import os,time\nfrom pathlib import Path\nPath({str(pidfile)!r}).write_text(str(os.getpid()))\ntime.sleep(60)')
        run, _ = start(client, lid)
        wait_for(pidfile.exists)
        client.post(f'/api/agent-runs/{run["id"]}/pause', json={})
    with pytest.raises(ProcessLookupError):
        os.kill(int(pidfile.read_text()), 0)


def test_other_server_cannot_start_an_agent_in_same_data_directory(client, tmp_path):
    from local_planner.agent_runs import AgentRuns
    from local_planner.domain.errors import Conflict
    lid = launcher(client, tmp_path, 'import time; time.sleep(30)')
    run, _ = start(client, lid)
    other_server = AgentRuns(tmp_path)
    with pytest.raises(Conflict):
        other_server.start('other', lid, 'second', lambda control: {'ok': True, 'status': 'succeeded'})
    client.post(f'/api/agent-runs/{run["id"]}/stop', json={})
    finished(client, run['id'])
    second = other_server.start('other', lid, 'second', lambda control: {'ok': True, 'status': 'succeeded'})
    wait_for(lambda: other_server.get(second['id'])['result'])
    other_server.close()


def test_request_id_cannot_be_reused_for_a_different_date(client, tmp_path):
    lid = launcher(client, tmp_path, 'print("ok")')
    run, body = start(client, lid, surface='day', date='2026-09-02')
    finished(client, run['id'])
    assert client.post('/api/agent-runs', json=body | {'date': '2026-09-03'}).status_code == 409
    assert client.post('/api/launchers/missing/run', json={'prompt': 'test'}).status_code == 404
