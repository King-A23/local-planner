from __future__ import annotations

import json
import sys
from pathlib import Path

from local_planner.clock import FrozenClock
from local_planner.launchers import (
    Launcher,
    add_launcher,
    compose_prompt,
    expand_command,
    load_launchers,
    run_launcher,
)
from local_planner.persistence import SqliteUnitOfWork
from local_planner.domain.commands import Planner

FROZEN = "2026-08-31T08:00:00+08:00"
STUB = Path(__file__).resolve().parent / "echo_stub.py"


def test_runner_passes_prompt_and_context(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_PLANNER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOCAL_PLANNER_ALLOW_CLOCK_OVERRIDE", "1")
    monkeypatch.setenv("LOCAL_PLANNER_CLOCK", FROZEN)
    proof = tmp_path / "proof.json"
    monkeypatch.setenv("LAUNCHER_PROOF", str(proof))

    uow = SqliteUnitOfWork.open(tmp_path / "planner.sqlite")
    planner = Planner(FrozenClock(FROZEN), uow)
    with uow.transaction():
        planner.add_to_inventory("库存一件")
        planner.add_todo_on_day("2026-08-31", "今天计划")
    uow.close()

    launcher = Launcher(
        id="stub",
        name="Stub",
        command=f"{sys.executable} {STUB} {{prompt}}",
    )
    result = run_launcher(
        launcher,
        "list today and add an errand",
        clock=FrozenClock(FROZEN),
        data_root=tmp_path,
    )
    assert result.ok is True
    assert result.stdout.strip() == "stub-ok"
    recorded = json.loads(proof.read_text(encoding="utf-8"))
    assert recorded["prompt"].endswith("list today and add an errand")
    assert "不要写 endClock" in recorded["prompt"]
    assert "list today and add an errand" in recorded["argv"][-1]
    context = json.loads(recorded["context"])
    assert context["today"] == "2026-08-31"
    assert any(item["title"] == "今天计划" for item in context["todos"])
    assert any(item["title"] == "库存一件" for item in context["inventory"])


def test_default_opencode_template_is_stored(tmp_path):
    items = load_launchers(tmp_path)
    assert any(
        item.command == "opencode run {prompt}"
        for item in items
    )
    added = add_launcher("Other", "echo {prompt}", tmp_path)
    names = {item.name for item in load_launchers(tmp_path)}
    assert added.name in names


def test_launcher_delivers_capabilities_and_executable_notes_example(tmp_path, monkeypatch):
    import shlex

    monkeypatch.setenv("LOCAL_PLANNER_ALLOW_CLOCK_OVERRIDE", "1")
    monkeypatch.setenv("LOCAL_PLANNER_CLOCK", FROZEN)
    root = tmp_path / "data with spaces"
    root.mkdir()
    uow = SqliteUnitOfWork.open(root / "planner.sqlite")
    with uow.transaction():
        Planner(FrozenClock(FROZEN), uow).add_todo_on_day("2026-08-31", "写报告")
    uow.close()
    stub = tmp_path / "notes_agent.py"
    stub.write_text('''import json, os, shlex, subprocess
from pathlib import Path
context = json.loads(Path(os.environ["LOCAL_PLANNER_CONTEXT_FILE"]).read_text())
assert "task.edit" in {c["name"] for c in context["capabilities"]["commands"]}
line = next(line for line in os.environ["LOCAL_PLANNER_PROMPT"].splitlines() if line.startswith("- 备注示例："))
args = shlex.split(line.split("：", 1)[1])
args[args.index("TASK_ID")] = context["todos"][0]["taskId"]
subprocess.run(args, check=True)
''')
    monkeypatch.chdir(tmp_path)
    result = run_launcher(
        Launcher("notes", "Notes", shlex.join([sys.executable, str(stub), "{prompt}"])),
        "给写报告补充备注：带上实验材料", clock=FrozenClock(FROZEN), data_root=root,
    )
    assert result.ok, result.stderr
    row = json.loads(result.stdout)["data"]["todos"][0]
    assert row["title"] == "写报告" and row["notes"] == "带上实验材料"


def test_expand_keeps_prompt_as_one_argv():
    argv = expand_command(
        "opencode run -m nassa-deepseek/deepseek-v4-flash {prompt}",
        "list today and add an errand",
        Path("/tmp/context.json"),
    )
    assert argv == [
        "opencode",
        "run",
        "-m",
        "nassa-deepseek/deepseek-v4-flash",
        "list today and add an errand",
    ]


def test_preset_prompt_forbids_invented_end_clock():
    text = compose_prompt("九点开始写设计")
    assert "九点开始写设计" in text
    assert "只写 startClock" in text
    assert "不要写 endClock" in text
    assert "编造结束时间" in text
    assert "day todo add today" in text
    assert "不要默认 inventory add" in text


def test_todo_page_defaults_to_inventory_unless_today():
    text = compose_prompt("买牛奶", surface="todo")
    assert "inventory add" in text
    assert "只有用户明确说是今天的任务" in text
    assert "不要 schedule" in text
    assert "以下默认仅适用于非定期事项" in text


def test_todo_page_daily_medication_must_use_recurrence_before_page_default():
    text = compose_prompt("我每天要吃药", surface="todo")
    command = (
        'python -m local_planner recurrence add --kind errand --title "吃药" '
        "--frequency daily --start-date today"
    )
    assert command in text
    assert text.index("定期事项（优先于页面默认写入规则）") < text.index("默认写入位置")
    assert "禁止降级为 inventory add、day todo add 或 day errand add 的单次事项" in text
    assert "明确的定期事项始终按前面的定期规则处理" in text


def test_recurrence_prompt_includes_complete_weekly_example():
    text = compose_prompt("每周五写周报")
    assert (
        'python -m local_planner recurrence add --kind plan --title "写周报" '
        "--frequency weekly --weekdays fri --start-date today"
    ) in text
    assert "只说“定期”但没有给出每天或每周几时" in text


def test_day_page_defaults_to_that_date():
    text = compose_prompt("答辩", surface="day", date="2026-09-03")
    assert "day todo add 2026-09-03" in text
    assert "不要默认 inventory add" in text
    assert "以下默认仅适用于非定期事项" in text


def test_codex_presets_upgrade_once_and_preserve_customizations(tmp_path):
    from local_planner.launchers import delete_launcher, update_launcher

    path = tmp_path / "launchers.json"
    path.write_text(json.dumps({"items": [
        {"id": "custom", "name": "Custom", "command": "echo {prompt}"}
    ]}))
    items = load_launchers(tmp_path)
    assert len(items) == 2
    assert items[0].id == "custom"
    preset = items[1]
    update_launcher(preset.id, "My Codex", "echo custom", tmp_path)
    assert load_launchers(tmp_path)[1].command == "echo custom"
    delete_launcher(preset.id, tmp_path)
    reloaded = load_launchers(tmp_path)
    assert [(item.id, item.name) for item in reloaded] == [("custom", "Custom")]


def test_codex_preset_uses_users_model_and_data_path(tmp_path):
    item = next(item for item in load_launchers(tmp_path) if item.id == "codex")
    argv = expand_command(item.command, "九点开始写设计", tmp_path / "context.json", tmp_path / "data with spaces")
    assert argv[:2] == ["codex", "exec"]
    assert "--model" not in argv
    assert argv[argv.index("--add-dir") + 1] == str(tmp_path / "data with spaces")
    assert argv[argv.index("--sandbox") + 1] == "workspace-write"
    assert argv[-1] == "九点开始写设计"


def test_runtime_prompt_cli_works_outside_project(tmp_path, monkeypatch):
    import shlex

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LOCAL_PLANNER_ALLOW_CLOCK_OVERRIDE", "1")
    monkeypatch.setenv("LOCAL_PLANNER_CLOCK", FROZEN)
    stub = tmp_path / "execute_example.py"
    stub.write_text('''import os, subprocess
prompt = os.environ["LOCAL_PLANNER_PROMPT"]
line = next(line for line in prompt.splitlines() if line.startswith("- 今天九点开始写设计："))
subprocess.run(line.split("：", 1)[1], shell=True, check=True)
''')
    result = run_launcher(
        Launcher("test", "test", shlex.join([sys.executable, str(stub), "{prompt}"])),
        "今天九点开始写设计", clock=FrozenClock(FROZEN), data_root=tmp_path / "data with spaces",
    )
    assert result.ok, result.stderr
    row = json.loads(result.stdout)["data"]["todos"][0]
    assert row["startClock"] == "09:00"
    assert row["endClock"] is None


def test_timeout_returns_text_and_stops_descendants(tmp_path):
    import shlex
    import subprocess

    stub = tmp_path / "timeout.py"
    child_pid = tmp_path / "child.pid"
    stub.write_text('''import subprocess, sys, time
from pathlib import Path
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
Path(sys.argv[1]).write_text(str(child.pid))
print("部分完成", flush=True)
print("错误输出", file=sys.stderr, flush=True)
time.sleep(60)
''')
    result = run_launcher(
        Launcher("test", "test", shlex.join([sys.executable, str(stub), str(child_pid)])),
        "test", timeout=0.5, clock=FrozenClock(FROZEN), data_root=tmp_path,
    )
    assert not result.ok
    assert "部分完成" in result.stdout
    assert "错误输出" in result.stderr
    assert "timeout" in result.stderr
    pid = child_pid.read_text()
    status = subprocess.run(["ps", "-o", "stat=", "-p", pid], capture_output=True, text=True)
    assert not status.stdout.strip() or status.stdout.strip().startswith("Z")


def test_repeated_invalid_tool_arguments_stop_early(tmp_path):
    import shlex
    import time

    stub = tmp_path / "invalid_tools.py"
    stub.write_text('''import sys, time
for _ in range(3):
    print("The bash tool was called with invalid arguments: SchemaError", file=sys.stderr, flush=True)
time.sleep(60)
''')
    started = time.monotonic()
    result = run_launcher(
        Launcher("test", "test", shlex.join([sys.executable, str(stub)])),
        "test", timeout=30, clock=FrozenClock(FROZEN), data_root=tmp_path,
    )
    assert not result.ok
    assert "工具参数格式反复出错" in result.stderr
    assert time.monotonic() - started < 10
