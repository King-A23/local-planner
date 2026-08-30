"""Cross-process flock, planner transaction, and adapter errors.

Dead rule: mkdir → flock (keep fd open) → then sqlite open.
The write transaction itself stays in SqliteUnitOfWork.transaction.
"""

from __future__ import annotations

import fcntl
import logging
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from local_planner.clock import Clock
from local_planner.domain.settlement import ensure_settled
from local_planner.domain.store import UnitOfWork
from local_planner.persistence import SqliteUnitOfWork

LOCK_TIMEOUT_SECONDS = 15
_POLL_SECONDS = 0.05


class LockTimeout(Exception):
    code = "LockTimeout"

    def __init__(self, message: str = "计划正忙，请重试") -> None:
        super().__init__(message)
        self.message = message


class InternalError(Exception):
    code = "InternalError"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(
            logging, os.environ.get("LOCAL_PLANNER_LOG", "INFO").upper(), logging.INFO
        )
    )


def _acquire_flock(fd: int, timeout: float) -> None:
    flags = fcntl.LOCK_EX | fcntl.LOCK_NB
    if timeout == 0:
        try:
            fcntl.flock(fd, flags)
        except BlockingIOError as exc:
            raise LockTimeout() from exc
        return
    deadline = time.monotonic() + timeout
    while True:
        try:
            fcntl.flock(fd, flags)
            return
        except BlockingIOError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LockTimeout()
            time.sleep(min(_POLL_SECONDS, remaining))


@contextmanager
def interprocess_lock(
    data_dir: Path, timeout: float | None = None
) -> Iterator[None]:
    if timeout is None:
        timeout = LOCK_TIMEOUT_SECONDS
    data_dir.mkdir(parents=True, exist_ok=True)
    fd = os.open(data_dir / "planner.lock", os.O_CREAT | os.O_RDWR, 0o644)
    acquired = False
    try:
        _acquire_flock(fd, timeout)
        acquired = True
        yield
    finally:
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


@contextmanager
def planner_txn(clock: Clock, uow: UnitOfWork) -> Iterator[str]:
    """Caller must already hold interprocess_lock. Yields today from inside the txn."""
    with uow.transaction():
        ensure_settled(clock, uow)
        yield clock.today()


@contextmanager
def exclusive_uow(
    data_dir: Path,
    sqlite_path: Path,
    timeout: float | None = None,
) -> Iterator[SqliteUnitOfWork]:
    """CLI only: lock → open → yield uow → close uow → unlock. Serve must not use this."""
    with interprocess_lock(data_dir, timeout=timeout):
        try:
            uow = SqliteUnitOfWork.open(sqlite_path)
        except sqlite3.Error as exc:
            raise InternalError("无法打开计划库") from exc
        try:
            yield uow
        finally:
            uow.close()


def open_persistent_uow(
    data_dir: Path,
    sqlite_path: Path,
    clock: Clock,
    timeout: float | None = None,
) -> SqliteUnitOfWork:
    """Serve startup only: lock → open → one planner_txn → unlock, uow stays open."""
    with interprocess_lock(data_dir, timeout=timeout):
        try:
            uow = SqliteUnitOfWork.open(sqlite_path)
        except sqlite3.Error as exc:
            raise InternalError("无法打开计划库") from exc
        try:
            with planner_txn(clock, uow):
                pass
        except Exception:
            uow.close()
            raise
        return uow


__all__ = [
    "LOCK_TIMEOUT_SECONDS",
    "LockTimeout",
    "InternalError",
    "configure_logging",
    "interprocess_lock",
    "planner_txn",
    "exclusive_uow",
    "open_persistent_uow",
]
