"""Cross-process flock: timeout, wait, persistence stays unlocked."""

from __future__ import annotations

import inspect
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest

from local_planner.backup import backup
from local_planner.clock import FrozenClock
from local_planner.http.serve import SettlementTimer, serve
from local_planner.persistence import SqliteUnitOfWork
from local_planner.runtime import (
    LOCK_TIMEOUT_SECONDS,
    LockTimeout,
    exclusive_uow,
    interprocess_lock,
    open_persistent_uow,
)

FROZEN = "2026-08-30T12:00:00+08:00"
SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "local_planner"

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
def holding_lock(data_dir: Path) -> Iterator[None]:
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


def test_persistence_has_no_flock() -> None:
    root = SRC_ROOT / "persistence"
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "interprocess_lock" not in text, path
        assert "fcntl" not in text, path
        assert "flock" not in text, path


def test_sqlite_open_still_works_without_planner_lock(tmp_path: Path) -> None:
    db = tmp_path / "planner.sqlite"
    uow = SqliteUnitOfWork.open(db)
    try:
        assert uow.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert not (tmp_path / "planner.lock").exists()
    finally:
        uow.close()


def test_exclusive_uow_locks_before_open() -> None:
    source = inspect.getsource(exclusive_uow)
    assert source.index("interprocess_lock") < source.index("SqliteUnitOfWork.open")
    open_src = inspect.getsource(SqliteUnitOfWork.open)
    assert "interprocess_lock" not in open_src
    assert "flock" not in open_src


def test_open_persistent_uow_locks_before_open() -> None:
    source = inspect.getsource(open_persistent_uow)
    assert source.index("interprocess_lock") < source.index("SqliteUnitOfWork.open")


def test_serve_uses_persistent_uow_not_exclusive() -> None:
    source = inspect.getsource(serve)
    assert "open_persistent_uow" in source
    assert "exclusive_uow" not in source


def test_exclusive_uow_times_out_when_other_process_holds_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("local_planner.runtime.LOCK_TIMEOUT_SECONDS", 0.2)
    db = tmp_path / "planner.sqlite"
    with holding_lock(tmp_path):
        started = time.monotonic()
        with pytest.raises(LockTimeout):
            with exclusive_uow(tmp_path, db):
                raise AssertionError("must not enter exclusive_uow")
        elapsed = time.monotonic() - started
        assert elapsed < 2
        assert not db.exists()
    with exclusive_uow(tmp_path, db) as uow:
        assert uow.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_open_persistent_uow_times_out_when_other_process_holds_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("local_planner.runtime.LOCK_TIMEOUT_SECONDS", 0.2)
    db = tmp_path / "planner.sqlite"
    clock = FrozenClock(FROZEN)
    with holding_lock(tmp_path):
        started = time.monotonic()
        with pytest.raises(LockTimeout):
            open_persistent_uow(tmp_path, db, clock)
        elapsed = time.monotonic() - started
        assert elapsed < 2
        assert not db.exists()
    uow = open_persistent_uow(tmp_path, db, clock)
    try:
        assert uow.meta.get("last_settled_date") == "2026-08-30"
    finally:
        uow.close()


def test_backup_times_out_when_other_process_holds_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCAL_PLANNER_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("local_planner.runtime.LOCK_TIMEOUT_SECONDS", 0.2)
    seed = SqliteUnitOfWork.open(tmp_path / "planner.sqlite")
    seed.close()
    with holding_lock(tmp_path):
        started = time.monotonic()
        with pytest.raises(LockTimeout):
            backup()
        elapsed = time.monotonic() - started
        assert elapsed < 2
        assert list((tmp_path / "backups").glob("planner-*.sqlite")) == []
    written = backup()
    assert written.exists()


def test_serve_lock_timeout_exits_3(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LOCAL_PLANNER_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("local_planner.runtime.LOCK_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr("local_planner.http.serve.uvicorn.run", lambda *a, **k: None)
    with holding_lock(tmp_path):
        started = time.monotonic()
        with pytest.raises(SystemExit) as excinfo:
            serve()
        elapsed = time.monotonic() - started
        assert excinfo.value.code == 3
        assert elapsed < 2
    assert "计划正忙" in capsys.readouterr().err


def test_settlement_timer_uses_timeout_zero() -> None:
    source = inspect.getsource(SettlementTimer._loop)
    assert "timeout=0" in source
    assert source.index("PLANNER_LOCK") < source.index("interprocess_lock")


def test_lock_timeout_constant_is_15() -> None:
    assert LOCK_TIMEOUT_SECONDS == 15


def test_interprocess_lock_zero_timeout_skips_immediately(tmp_path: Path) -> None:
    with holding_lock(tmp_path):
        started = time.monotonic()
        with pytest.raises(LockTimeout):
            with interprocess_lock(tmp_path, timeout=0):
                raise AssertionError("must not acquire")
        assert time.monotonic() - started < 0.5
