import json


def test_planning_cli_preview_save_and_safe_revert(planner_home, run_cli):
    def cli(*argv):
        code, payload, _ = run_cli(list(argv))
        assert code == 0, payload
        return payload['data']

    draft = cli('planning', 'create', '--request-id', 'create', '--recovery-generation', 'none')
    path = planner_home / 'draft.json'
    path.write_text(json.dumps({'goals': [{'id': 'goal', 'title': 'Learn', 'actions': [{'id': 'action', 'title': 'Read'}]}]}))

    def change(draft, operation, *extra):
        return cli('planning', operation, draft['id'], '--expected-revision', str(draft['revision']),
                   '--request-id', operation, '--recovery-generation', 'none', *extra)

    draft = change(draft, 'update', '--document-file', str(path))
    assert cli('goal', 'list')['items'] == []
    assert cli('planning', 'show', draft['id'])['canUndo']
    draft = change(draft, 'apply')
    assert draft['canRevert']
    assert cli('inventory', 'list')['items'] == []
    assert cli('goal', 'show', 'goal')['actions'][0]['taskId'] is None
    assert change(draft, 'revert')['status'] == 'discarded'
    assert cli('goal', 'show', 'goal')['state'] == 'ended'


def test_goal_cli_stale_recovery_reports_conflict(planner_home, run_cli):
    code, payload, _ = run_cli(['goal', 'create', '--title', 'Stale', '--request-id', 'create',
                                '--recovery-generation', 'old'])
    assert code == 1
    assert payload['error']['code'] == 'Conflict'
