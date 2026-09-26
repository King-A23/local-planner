"""CLI backup uses the SQLite backup API (WAL-safe), not a raw file copy."""

from __future__ import annotations

import inspect
import json
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from local_planner.__main__ import main
from local_planner.backup import backup
from local_planner.clock import FrozenClock
from local_planner.domain.commands import Planner
from local_planner.persistence import SqliteUnitOfWork

TODAY = "2026-08-30"
FROZEN = "2026-08-30T12:00:00+08:00"


def _seed(db: Path) -> None:
    uow = SqliteUnitOfWork.open(db)
    planner = Planner(clock=FrozenClock(FROZEN), uow=uow)
    with uow.transaction():
        planner.add_todo_on_day(TODAY, "备份这一条")
    # leave the connection open until the caller closes — WAL may be present
    uow.close()


def test_backup_cli_default_dir(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_PLANNER_DATA_DIR", str(tmp_path))
    _seed(tmp_path / "planner.sqlite")
    assert main(["backup"]) == 0
    out = capsys.readouterr().out
    backups = list((tmp_path / "backups").glob("planner-*.sqlite"))
    assert len(backups) == 1
    dest = backups[0]
    assert str(dest) in out
    titles = [
        row[0]
        for row in sqlite3.connect(dest).execute("SELECT title FROM tasks")
    ]
    assert titles == ["备份这一条"]


def test_backup_while_source_is_open(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_PLANNER_DATA_DIR", str(tmp_path))
    db = tmp_path / "planner.sqlite"
    uow = SqliteUnitOfWork.open(db)
    planner = Planner(clock=FrozenClock(FROZEN), uow=uow)
    with uow.transaction():
        planner.add_todo_on_day(TODAY, "还开着")
    dest = backup()
    try:
        probe = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
        titles = [row[0] for row in probe.execute("SELECT title FROM tasks")]
        probe.close()
        assert titles == ["还开着"]
    finally:
        uow.close()


def test_backup_to_user_path_and_directory(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("LOCAL_PLANNER_DATA_DIR", str(tmp_path))
    _seed(tmp_path / "planner.sqlite")
    file_dest = tmp_path / "out" / "copy.sqlite"
    assert main(["backup", str(file_dest)]) == 0
    assert file_dest.exists()
    assert "已备份到" in capsys.readouterr().out
    dir_dest = tmp_path / "copies"
    dir_dest.mkdir()
    assert main(["backup", str(dir_dest)]) == 0
    copies = list(dir_dest.glob("planner-*.sqlite"))
    assert len(copies) == 1


def test_backup_refuses_missing_db_and_overwrite(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("LOCAL_PLANNER_DATA_DIR", str(tmp_path))
    assert main(["backup"]) == 1
    err = capsys.readouterr().err
    assert "找不到数据库" in err
    _seed(tmp_path / "planner.sqlite")
    dest = tmp_path / "exists.sqlite"
    dest.write_bytes(b"x")
    assert main(["backup", str(dest)]) == 1
    assert "目标已存在" in capsys.readouterr().err
    assert dest.read_bytes() == b"x"


def test_backup_too_many_args(capsys) -> None:
    assert main(["backup", "a", "b"]) == 1
    assert "用法" in capsys.readouterr().err


_HOLDER = """
import fcntl, os, sys, time
from pathlib import Path
data_dir = Path(sys.argv[1])
ready, release = Path(sys.argv[2]), Path(sys.argv[3])
data_dir.mkdir(parents=True, exist_ok=True)
fd = os.open(data_dir / "planner.lock", os.O_CREAT | os.O_RDWR, 0o644)
fcntl.flock(fd, fcntl.LOCK_EX)
ready.write_text("1", encoding="utf-8")
while not release.exists():
    time.sleep(0.02)
os.close(fd)
"""


@contextmanager
def _holding_lock(data_dir: Path) -> Iterator[None]:
    ready = data_dir / ".holder-ready"
    release = data_dir / ".holder-release"
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(data_dir), str(ready), str(release)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 5
        while not ready.exists():
            if proc.poll() is not None:
                err = (proc.stderr.read() or b"").decode()
                raise RuntimeError(f"lock holder exited: {err}")
            if time.monotonic() > deadline:
                raise TimeoutError("lock holder did not become ready")
            time.sleep(0.01)
        yield
    finally:
        release.write_text("1", encoding="utf-8")
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


def test_backup_lock_timeout_is_exit_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LOCAL_PLANNER_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("local_planner.runtime.LOCK_TIMEOUT_SECONDS", 0.2)
    _seed(tmp_path / "planner.sqlite")
    with _holding_lock(tmp_path):
        started = time.monotonic()
        assert main(["backup"]) == 3
        elapsed = time.monotonic() - started
        assert elapsed < 3
    err = capsys.readouterr().err.strip()
    assert "计划正忙" in err
    with pytest.raises(json.JSONDecodeError):
        json.loads(err)
    assert list((tmp_path / "backups").glob("planner-*.sqlite")) == []


def test_backup_module_does_not_import_http() -> None:
    import local_planner.backup as backup_mod

    source = inspect.getsource(backup_mod)
    assert "local_planner.http" not in source
