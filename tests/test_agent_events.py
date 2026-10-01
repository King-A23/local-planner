"""Public event filtering, wire limits and direct launcher compatibility."""
import json

from local_planner.agent_events import EventBuffer, PublicEvents, structured_command


def test_only_direct_known_launchers_get_json_flags():
    original = ['codex', 'exec', '--model', 'gpt-6-luna', '-c', 'model_reasoning_effort="medium"', 'prompt']
    argv, source = structured_command(original)
    assert source == 'codex' and argv[2] == '--json'
    assert argv[:2] + argv[3:] == original
    assert '--json' not in original
    assert structured_command(argv) == (argv, 'codex')
    assert structured_command(['opencode', 'run', '-m', 'provider/model', 'prompt']) == (['opencode', 'run', '--format', 'json', '-m', 'provider/model', 'prompt'], 'opencode')
    for args in [['env', 'codex', 'exec', 'prompt'], ['bash', '-c', 'codex exec prompt'], ['wrapper', 'codex', 'exec'], ['codex', 'review'], ['opencode', 'run', '--format', 'default', 'prompt']]:
        assert structured_command(args) == (args, 'none')


def test_codex_filters_reasoning_and_keeps_only_final_reply():
    buffer = EventBuffer()
    parser = PublicEvents('codex', buffer)
    events = [
        {'type': 'item.completed', 'item': {'id': 'secret', 'type': 'reasoning', 'text': 'hidden-secret'}},
        {'type': 'item.completed', 'item': {'id': 'message', 'type': 'agent_message', 'phase': 'commentary', 'text': '先读取今天的计划'}},
        {'type': 'item.started', 'item': {'id': 'tool', 'type': 'command_execution', 'command': 'python -m local_planner day open today'}},
        {'type': 'item.completed', 'item': {'id': 'tool', 'type': 'command_execution', 'command': 'python -m local_planner day open today', 'aggregated_output': '中文 🐈', 'exit_code': 1}},
        {'type': 'item.completed', 'item': {'id': 'reply', 'type': 'agent_message', 'text': '请确认日期'}},
    ]
    raw = '\n'.join(json.dumps(e, ensure_ascii=False) for e in events) + '\n'
    for char in raw:
        parser.feed(char)
    payload = buffer.payload(0)
    assert 'hidden-secret' not in json.dumps(payload)
    assert parser.reply == '请确认日期'
    operations = [item for item in payload['items'] if item['itemId'] == 'tool']
    assert [e['status'] for e in operations] == ['running', 'failed']
    assert operations[0]['summary'] == '读取当天计划'
    assert '中文 🐈' in operations[-1]['details']
    assert buffer.payload(operations[0]['sequence'])['items'][0] == operations[1]


def test_malformed_unknown_and_oversized_events_do_not_fail_execution():
    parser = PublicEvents('codex', EventBuffer())
    for raw in ['bad\n', '[]\n', '{"type":"item.started","item":[]}\n', '{"type":"future.event"}\n', '{"type":[]}\n']:
        parser.feed(raw)
    parser.feed('x' * (1024 * 1024 + 1))
    parser.feed('\n')
    parser.feed(json.dumps({'type': 'item.completed', 'item': {'id': 'final', 'type': 'agent_message', 'text': '完成'}}), final=True)
    assert parser.reply == '完成'
    assert not parser.failed


def test_event_buffer_is_bounded_in_count_and_wire_bytes():
    buffer = EventBuffer()
    buffer.set_source('codex')
    for i in range(600):
        buffer.emit(str(i), 'operation', 'completed', '中文摘要', '中' * 10000)
    payload = buffer.payload(0)
    assert payload['truncated'] and payload['nextSequence'] == 600
    assert len(payload['items']) < 500 and buffer.size <= 256 * 1024
    assert all(len(item['details'].encode()) <= 8192 for item in payload['items'])
    assert all('内容已省略' in item['details'] for item in payload['items'])
    assert buffer.payload(600)['items'] == []
    small = EventBuffer()
    for i in range(600): small.emit(str(i), 'status', 'completed', 'ok')
    assert len(small.payload(0)['items']) == 500


def test_opencode_public_text_and_tools_exclude_reasoning():
    buffer = EventBuffer()
    parser = PublicEvents('opencode', buffer)
    for event in [
        {'type': 'reasoning', 'part': {'id': 'secret', 'text': 'private'}},
        {'type': 'text', 'part': {'id': 'explain', 'text': '先核对'}},
        {'type': 'tool_use', 'part': {'id': 'tool', 'tool': 'bash', 'state': {'status': 'completed', 'input': {'command': 'python -m local_planner inventory list'}, 'output': '[]'}}},
        {'type': 'text', 'part': {'id': 'final', 'text': '没有待办'}},
    ]:
        parser.feed(json.dumps(event) + '\n')
    assert parser.reply == '没有待办'
    assert 'private' not in json.dumps(buffer.payload(0))
    assert buffer.payload(0)['items'][1]['summary'] == '读取待办'


def test_structured_failure_is_a_failure_even_if_cli_exits_zero():
    parser = PublicEvents('codex', EventBuffer())
    parser.feed('{"type":"turn.failed","error":{"message":"连接失败"}}\n')
    assert parser.failed and parser.error == '连接失败'


def test_shell_enveloped_planner_operation_has_readable_summary():
    from local_planner.agent_events import operation_summary
    assert operation_summary('command_execution', "/bin/zsh -lc 'env LOCAL_PLANNER_DATA_DIR=/tmp/data python -m local_planner inventory list'") == '读取待办'


def test_public_messages_remove_internal_process_markers():
    buffer = EventBuffer()
    parser = PublicEvents('codex', buffer)
    parser.feed(json.dumps({'type': 'item.completed', 'item': {'id': 'final', 'type': 'agent_message', 'text': '草案已生成\n\n`PROCESS_CLEANUP_COMPLETE`'}}) + '\n')
    assert parser.reply == '草案已生成'
    assert 'PROCESS_CLEANUP' not in json.dumps(buffer.payload(0))


def test_no_recognizable_public_events_reports_process_unavailable():
    buffer = EventBuffer()
    parser = PublicEvents('codex', buffer)
    parser.feed('bad\n{"type":"future.event"}\n', final=True)
    assert buffer.payload(0)['source'] == 'none'
    assert not parser.failed and parser.reply == ''
