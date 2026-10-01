"""Real pipes prove progress arrives before completion and stays under supervision."""
import shlex
import sys
import time
import uuid

from tests.http.test_agent_runs import wait_for, finished


def direct_stub(client, tmp_path, source):
    path = tmp_path / 'codex'
    path.write_text(f'#!{sys.executable}\n' + source)
    path.chmod(0o755)
    return client.post('/api/launchers', json={'name': 'JSON progress stub', 'command': shlex.join([str(path), 'exec', '{prompt}'])}).json()['id']


def start(client, lid):
    res = client.post('/api/agent-runs', json={'launcherId': lid, 'requestId': str(uuid.uuid4()), 'prompt': 'progress'})
    assert res.status_code == 202, res.text
    return res.json()['id']


def test_progress_before_finish_pause_refresh_resume_and_final_reply(client, tmp_path):
    lid = direct_stub(client, tmp_path, '''import json,time,sys,os
assert '--json' in sys.argv
print(json.dumps({'type':'item.completed','item':{'id':'comment','type':'agent_message','phase':'commentary','text':'正在读取计划'}}),flush=True)
print(json.dumps({'type':'item.started','item':{'id':'tool','type':'command_execution','command':'python -m local_planner context'}}),flush=True)
sys.stderr.write('诊断信息\\n');sys.stderr.flush()
time.sleep(.8)
print(json.dumps({'type':'item.completed','item':{'id':'tool','type':'command_execution','command':'python -m local_planner context','exit_code':0}}),flush=True)
print(json.dumps({'type':'item.completed','item':{'id':'final','type':'agent_message','text':'结果完成'}}),flush=True)
''')
    rid = start(client, lid)
    events_url = f'/api/agent-runs/{rid}/events'
    before = wait_for(lambda: client.get(events_url).json(), lambda data: len(data['items']) >= 2)
    assert client.get(f'/api/agent-runs/{rid}').json()['result'] is None
    assert before['source'] == 'codex'
    assert client.post(f'/api/agent-runs/{rid}/pause', json={}).status_code == 200
    paused = client.get(events_url).json()
    time.sleep(.9)
    assert client.get(events_url).json() == paused
    assert client.get('/api/agent-runs').json()['run']['id'] == rid
    assert client.post(f'/api/agent-runs/{rid}/resume', json={}).status_code == 200
    result = finished(client, rid)
    assert result['result']['stdout'] == '结果完成'
    assert '诊断信息' in result['result']['stderr']
    after = client.get(events_url, params={'after': before['nextSequence']}).json()
    assert any(item['itemId'] == 'tool' and item['status'] == 'completed' for item in after['items'])
    assert client.get(events_url, params={'after': -1}).status_code == 400
    assert client.get('/api/agent-runs/missing/events').status_code == 404


def test_split_utf8_simultaneous_large_pipes_and_stop(client, tmp_path):
    lid = direct_stub(client, tmp_path, '''import json,os,time,threading
raw=(json.dumps({'type':'item.completed','item':{'id':'message','type':'agent_message','text':'中文🐈'}},ensure_ascii=False)+'\\n').encode()
for byte in raw: os.write(1,bytes([byte]))
t=threading.Thread(target=lambda: os.write(2,b'diagnostic'*20000));t.start()
for i in range(600):
 os.write(1,(json.dumps({'type':'item.completed','item':{'id':str(i),'type':'command_execution','command':'echo test','aggregated_output':'中'*5000,'exit_code':0}},ensure_ascii=False)+'\\n').encode())
t.join()
time.sleep(20)
''')
    rid = start(client, lid)
    url = f'/api/agent-runs/{rid}/events'
    batch = wait_for(lambda: client.get(url).json(), lambda data: data['nextSequence'] >= 601)
    assert batch['truncated'] and len(batch['items']) <= 500
    assert all(len(e.get('details','').encode()) <= 8192 for e in batch['items'])
    assert client.post(f'/api/agent-runs/{rid}/stop', json={}).status_code == 200
    result = finished(client, rid)
    assert result['status'] == 'stopped'
    assert result['result']['stdout'] == '中文🐈'
    assert len(result['result']['stderr']) == len('diagnostic') * 20000


def test_closed_pipes_still_obey_timeout(client, tmp_path, monkeypatch):
    import local_planner.http.app as app_module
    original = app_module.run_launcher
    def short_run(*args, **kwargs):
        return original(*args, **(kwargs | {'timeout': .15}))
    monkeypatch.setattr(app_module, 'run_launcher', short_run)
    lid = direct_stub(client, tmp_path, 'import os,time\nos.close(1);os.close(2);time.sleep(20)\n')
    rid = start(client, lid)
    result = finished(client, rid)
    assert result['status'] == 'failed'
    assert 'timeout' in result['result']['stderr']


def test_structured_failure_preserves_receipt_without_success_claim(client, tmp_path):
    lid = direct_stub(client, tmp_path, 'print(\'{"type":"turn.failed","error":{"message":"连接失败"}}\',flush=True)\n')
    result = finished(client, start(client, lid))
    assert result['status'] == 'failed'
    assert result['result']['stdout'] == ''
    assert result['result']['stderr'].strip() == '连接失败'
