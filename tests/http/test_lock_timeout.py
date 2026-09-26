"""HTTP maps LockTimeout to 503; health stays unlocked; timer skip is non-blocking."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from local_planner.clock import FrozenClock
from local_planner.http.app import create_app
from local_planner.http.serve import SettlementTimer
from local_planner.persistence import SqliteUnitOfWork

FROZEN = "2026-08-30T12:00:00+08:00"
PROD_DIR = Path.home() / "Library" / "Application Support" / "local-planner"

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


def test_get_meta_is_503_when_lock_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("local_planner.runtime.LOCK_TIMEOUT_SECONDS", 0.2)
    clock = FrozenClock(FROZEN)
    uow = SqliteUnitOfWork.open(tmp_path / "planner.sqlite")
    try:
        app = create_app(
            clock=clock, uow=uow, port=8787, dev=False, data_dir=tmp_path
        )
        with holding_lock(tmp_path):
            with TestClient(app, base_url="http://127.0.0.1:8787") as client:
                started = time.monotonic()
                health = client.get("/api/health")
                assert health.status_code == 200
                assert health.json() == {"ok": True, "service": "local-planner"}
                meta = client.get("/api/meta")
                elapsed = time.monotonic() - started
                assert meta.status_code == 503
                body = meta.json()
                assert body["error"] == "LockTimeout"
                assert "message" in body
                dumped = json.dumps(body)
                assert str(tmp_path) not in dumped
                assert "Application Support" not in dumped
                assert elapsed < 3
    finally:
        uow.close()


def test_timer_skip_does_not_block_http_503(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr("local_planner.runtime.LOCK_TIMEOUT_SECONDS", 0.2)
    clock = FrozenClock(FROZEN)
    uow = SqliteUnitOfWork.open(tmp_path / "planner.sqlite")
    timer = SettlementTimer(clock, uow, tmp_path, interval=0.05)
    try:
        app = create_app(
            clock=clock, uow=uow, port=8787, dev=False, data_dir=tmp_path
        )
        with holding_lock(tmp_path):
            with caplog.at_level(logging.INFO, logger="local_planner.http.serve"):
                timer.start()
                time.sleep(0.2)
                with TestClient(app, base_url="http://127.0.0.1:8787") as client:
                    started = time.monotonic()
                    meta = client.get("/api/meta")
                    elapsed = time.monotonic() - started
                    assert meta.status_code == 503
                    assert meta.json()["error"] == "LockTimeout"
                    assert elapsed < 3
                    assert client.get("/api/health").status_code == 200
            assert any(
                "code=LockTimeout wait_s=0 skip" in rec.getMessage()
                for rec in caplog.records
            )
    finally:
        timer.stop()
        uow.close()


def test_create_app_does_not_use_production_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LOCAL_PLANNER_DATA_DIR", raising=False)
    monkeypatch.delenv("LOCAL_PLANNER_DEV", raising=False)
    prod_lock = PROD_DIR / "planner.lock"
    existed = prod_lock.exists()
    before = prod_lock.stat().st_mtime_ns if existed else None
    clock = FrozenClock(FROZEN)
    uow = SqliteUnitOfWork.open(tmp_path / "planner.sqlite")
    try:
        app = create_app(clock=clock, uow=uow, port=8787, dev=False)
        with TestClient(app, base_url="http://127.0.0.1:8787") as client:
            assert client.get("/api/meta").status_code == 200
        assert (tmp_path / "planner.lock").exists()
        if existed:
            assert prod_lock.stat().st_mtime_ns == before
        else:
            assert not prod_lock.exists()
    finally:
        uow.close()
