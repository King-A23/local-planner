"""CLI tests use a temp data dir and a frozen Shanghai clock."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from local_planner.__main__ import main

FROZEN = "2026-08-31T08:00:00+08:00"
TODAY = "2026-08-31"
YESTERDAY = "2026-08-30"


@pytest.fixture
def planner_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LOCAL_PLANNER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOCAL_PLANNER_ALLOW_CLOCK_OVERRIDE", "1")
    monkeypatch.setenv("LOCAL_PLANNER_CLOCK", FROZEN)
    monkeypatch.delenv("LOCAL_PLANNER_DEV", raising=False)
    return tmp_path


@pytest.fixture
def run_cli(capsys: pytest.CaptureFixture[str]):
    def _run(argv: list[str]) -> tuple[int, dict, str]:
        code = main(argv)
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        return code, payload, captured.err

    return _run
