"""Placeholder so pytest collects a passing suite. No product logic."""

from __future__ import annotations

import pytest

from local_planner import __version__
from local_planner.__main__ import main


def test_package_imports() -> None:
    assert __version__


def test_help_exits_zero() -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0


def test_unimplemented_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["serve"]) == 1
    captured = capsys.readouterr()
    assert "未实现" in captured.err
