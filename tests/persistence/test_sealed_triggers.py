"""Item 35: sealed-day SQL mutations must ABORT. Direct SQL, not domain guards."""

from __future__ import annotations

import sqlite3

import pytest

from local_planner.clock import FrozenClock
from local_planner.domain.commands import Planner
from local_planner.persistence.store import SqliteUnitOfWork

TODAY = "2026-08-30"

SEALED_MSG = "sealed day is immutable"


def _seed_sealed(uow: SqliteUnitOfWork, clock: FrozenClock) -> tuple[str, str]:
    planner = Planner(clock=clock, uow=uow)
    with uow.transaction():
        day = planner.add_todo_on_day(TODAY, "待办")
        day = planner.add_errand(TODAY, "差事")
        planner.seal_day(TODAY)
    tid = day.todos[0].task_id
    eid = day.errands[0].id
    return tid, eid


def test_sealed_day_task_entry_insert_update_delete_abort(
    uow: SqliteUnitOfWork, clock: FrozenClock
) -> None:
    tid, _ = _seed_sealed(uow, clock)
    uow.conn.execute(
        "INSERT INTO tasks (id, title, created_at, current_scheduled_date, completed_at, completed_on_date) "
        "VALUES ('other', '另一件', '2026-08-30T04:00:00Z', NULL, NULL, NULL)"
    )
    with pytest.raises(sqlite3.IntegrityError, match=SEALED_MSG):
        uow.conn.execute(
            "INSERT INTO day_task_entries (day_date, task_id, title_snapshot, sort_order, completed_on_day) "
            "VALUES (?, 'other', '另一件', 99, 0)",
            (TODAY,),
        )
    with pytest.raises(sqlite3.IntegrityError, match=SEALED_MSG):
        uow.conn.execute(
            "UPDATE day_task_entries SET title_snapshot = '篡改' WHERE day_date = ? AND task_id = ?",
            (TODAY, tid),
        )
    with pytest.raises(sqlite3.IntegrityError, match=SEALED_MSG):
        uow.conn.execute(
            "DELETE FROM day_task_entries WHERE day_date = ? AND task_id = ?",
            (TODAY, tid),
        )
    row = uow.conn.execute(
        "SELECT title_snapshot FROM day_task_entries WHERE day_date = ? AND task_id = ?",
        (TODAY, tid),
    ).fetchone()
    assert row[0] == "待办"


def test_sealed_errand_insert_update_delete_abort(
    uow: SqliteUnitOfWork, clock: FrozenClock
) -> None:
    _, eid = _seed_sealed(uow, clock)
    with pytest.raises(sqlite3.IntegrityError, match=SEALED_MSG):
        uow.conn.execute(
            "INSERT INTO errands (id, day_date, title, sort_order, status, completed_at) "
            "VALUES ('e-new', ?, '新差事', 99, 'open', NULL)",
            (TODAY,),
        )
    with pytest.raises(sqlite3.IntegrityError, match=SEALED_MSG):
        uow.conn.execute(
            "UPDATE errands SET title = '篡改' WHERE id = ?",
            (eid,),
        )
    with pytest.raises(sqlite3.IntegrityError, match=SEALED_MSG):
        uow.conn.execute("DELETE FROM errands WHERE id = ?", (eid,))
    row = uow.conn.execute("SELECT title FROM errands WHERE id = ?", (eid,)).fetchone()
    assert row[0] == "差事"


def test_sealed_day_unseal_mutate_sealed_at_and_delete_abort(
    uow: SqliteUnitOfWork, clock: FrozenClock
) -> None:
    _seed_sealed(uow, clock)
    original = uow.conn.execute(
        "SELECT status, sealed_at FROM days WHERE date = ?", (TODAY,)
    ).fetchone()
    assert original[0] == "sealed"
    assert original[1] is not None

    with pytest.raises(sqlite3.IntegrityError, match=SEALED_MSG):
        uow.conn.execute(
            "UPDATE days SET status = 'open', sealed_at = NULL WHERE date = ?",
            (TODAY,),
        )
    with pytest.raises(sqlite3.IntegrityError, match=SEALED_MSG):
        uow.conn.execute(
            "UPDATE days SET sealed_at = '2099-01-01T00:00:00Z' WHERE date = ?",
            (TODAY,),
        )
    with pytest.raises(sqlite3.IntegrityError, match=SEALED_MSG):
        uow.conn.execute("DELETE FROM days WHERE date = ?", (TODAY,))

    after = uow.conn.execute(
        "SELECT status, sealed_at FROM days WHERE date = ?", (TODAY,)
    ).fetchone()
    assert after[0] == "sealed"
    assert after[1] == original[1]
