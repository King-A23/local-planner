"""Package import, CLI help, and README run-docs contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from local_planner import __version__
from local_planner.__main__ import main

README = Path(__file__).resolve().parents[1] / "README.md"


def test_package_imports() -> None:
    assert __version__


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--help"]) == 0
    captured = capsys.readouterr()
    assert "inventory list" in captured.out
    assert "recurrence add --kind {plan,errand}" in captured.out
    assert "recurrence pause|resume|stop SERIES_ID" in captured.out


def test_unknown_command(capsys: pytest.CaptureFixture[str]) -> None:
    import json

    assert main(["not-a-command"]) == 2
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "UsageError"


def test_readme_advertises_loopback_backup_reset_and_debug() -> None:
    text = README.read_text(encoding="utf-8")
    assert "http://127.0.0.1:8787" in text
    assert "npm run build" in text
    assert "python -m local_planner serve" in text
    assert "local-todo" in text
    assert "local-todo serve" in text
    assert "python -m local_planner backup" in text
    assert "/api/debug" in text
    assert "planner.sqlite-wal" in text
    assert "Asia/Shanghai" in text
    assert "不要用 `http://localhost:8787`" in text
    advertised = [
        line
        for line in text.splitlines()
        if "http://localhost" in line and "不要用" not in line
    ]
    assert advertised == []
    assert "搜索" not in text or "不做搜索" in text
