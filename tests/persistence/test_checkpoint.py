from __future__ import annotations

from pathlib import Path

from local_planner.clock import FrozenClock
from local_planner.domain.commands import Planner
from local_planner.persistence import SqliteUnitOfWork
from local_planner.persistence.checkpoint import restore_connection, snapshot_connection

FROZEN = "2026-08-31T08:00:00+08:00"


def test_snapshot_restore_drops_later_writes(tmp_path: Path) -> None:
    uow = SqliteUnitOfWork.open(tmp_path / "planner.sqlite")
    planner = Planner(FrozenClock(FROZEN), uow)
    try:
        with uow.transaction():
            planner.add_to_inventory("留下")
        snap = tmp_path / "agent-checkpoint.sqlite"
        snapshot_connection(uow.conn, snap)
        with uow.transaction():
            planner.add_to_inventory("应撤回")
        assert {item.task.title for item in planner.list_inventory()} == {
            "留下",
            "应撤回",
        }
        restore_connection(uow.conn, snap)
        assert [item.task.title for item in planner.list_inventory()] == ["留下"]
    finally:
        uow.close()
