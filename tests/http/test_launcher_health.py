import shlex
import sys

from local_planner.launchers import load_launchers, save_launchers, Launcher


def make(client, command):
    return client.post('/api/launchers', json={'name': 'Check stub', 'command': command}).json()['id']


def test_check_missing_and_invalid_without_running_custom_command(client, tmp_path):
    lid = make(client, 'nonexistent-planner-agent-tool {prompt}')
    assert client.post(f'/api/launchers/{lid}/check').json()['status'] == 'missing'
    proof = tmp_path / 'must-not-run'
    lid = make(client, shlex.join([sys.executable, '-c', f'open({str(proof)!r}, "w").close()']))
    checked = client.post(f'/api/launchers/{lid}/check').json()
    assert checked['status'] == 'installed'
    assert not proof.exists()
    lid = make(client, 'unterminated "')
    assert client.post(f'/api/launchers/{lid}/check').json()['status'] == 'invalid'


def test_codex_check_only_runs_status_and_never_exposes_output(client, tmp_path):
    binary = tmp_path / 'codex'
    binary.write_text('#!/bin/sh\n[ "$1 $2" = "login status" ] || exit 9\necho SECRET_DO_NOT_SHOW\nexit 0\n')
    binary.chmod(0o755)
    lid = make(client, shlex.join([str(binary), 'exec', 'never run this']))
    response = client.post(f'/api/launchers/{lid}/check')
    assert response.json()['status'] == 'ready'
    assert 'SECRET_DO_NOT_SHOW' not in response.text
    binary.write_text('#!/bin/sh\necho "Not logged in" >&2\nexit 1\n')
    assert client.post(f'/api/launchers/{lid}/check').json()['status'] == 'login_required'
    binary.write_text('#!/bin/sh\necho "bad config" >&2\nexit 1\n')
    assert client.post(f'/api/launchers/{lid}/check').json()['status'] == 'unknown'


def test_saved_user_config_is_not_overwritten(tmp_path):
    original = Launcher('personal', '我的模型', 'opencode run -m my-provider/my-model {prompt}')
    save_launchers([original], tmp_path)
    assert load_launchers(tmp_path) == [original]
