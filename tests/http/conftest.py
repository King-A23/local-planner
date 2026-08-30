"""HTTP fixtures: temp SQLite + FrozenClock. Never the real data dir."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from local_planner.clock import FrozenClock
from local_planner.http.app import create_app
from local_planner.persistence import SqliteUnitOfWork

FROZEN = "2026-08-30T12:00:00+08:00"
TODAY = "2026-08-30"


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(FROZEN)


@pytest.fixture
def uow(tmp_path: Path) -> Iterator[SqliteUnitOfWork]:
    store = SqliteUnitOfWork.open(tmp_path / "planner.sqlite")
    try:
        yield store
    finally:
        store.close()


@pytest.fixture
def app(clock: FrozenClock, uow: SqliteUnitOfWork):
    return create_app(clock=clock, uow=uow, port=8787, dev=False)


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://127.0.0.1:8787") as test_client:
        yield test_client
