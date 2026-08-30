"""SQLite persistence fixtures. Temp files only — not the real data dir."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from local_planner.clock import FrozenClock
from local_planner.persistence import SqliteUnitOfWork

FROZEN = "2026-08-30T12:00:00+08:00"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "planner.sqlite"


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(FROZEN)


@pytest.fixture
def uow(db_path: Path) -> Iterator[SqliteUnitOfWork]:
    store = SqliteUnitOfWork.open(db_path)
    try:
        yield store
    finally:
        store.close()
