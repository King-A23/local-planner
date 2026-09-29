"""Schema v1 CHECKs, FKs, pragmas, reopen, and domain commands via SQLite UoW."""

from __future__ import annotations

import inspect
import sqlite3
from pathlib import Path

import pytest

from local_planner.clock import FrozenClock
from local_planner.domain.commands import Planner
from local_planner.domain.errors import Conflict
from local_planner.domain.models import DayTaskEntry, task_status
from local_planner.persistence import SqliteUnitOfWork, open_connection
from local_planner.persistence import connection as connection_mod
from local_planner.persistence import store as store_mod

TODAY = "2026-08-30"

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "local_planner"


def test_open_sets_required_connection_pragmas(uow: SqliteUnitOfWork) -> None:
    assert uow.conn.isolation_level is None
    assert uow.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert uow.conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert uow.conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    assert uow.conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_connect_kwargs_are_autocommit_and_cross_thread() -> None:
    source = inspect.getsource(open_connection)
    assert "isolation_level=None" in source
    assert "check_same_thread=False" in source


def test_schema_v1_tables_indexes_triggers_and_meta(uow: SqliteUnitOfWork) -> None:
    tables = {
        row[0]
        for row in uow.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {
        "schema_migrations",
        "meta",
        "days",
        "tasks",
        "day_task_entries",
        "errands",
        "recurrence_series",
        "recurrence_occurrences",
        "day_planning",
        "goals",
        "goal_phases",
            "goal_requests",
            "goal_actions",
            "goal_action_requests",
            "planning_drafts",
            "planning_requests",
    } <= tables
    triggers = {
        row[0]
        for row in uow.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        )
    }
    assert triggers == {
        "day_task_entries_no_insert_sealed",
        "day_task_entries_no_update_sealed",
        "day_task_entries_no_delete_sealed",
        "errands_no_insert_sealed",
        "errands_no_update_sealed",
        "errands_no_delete_sealed",
        "days_no_unseal_or_mutate_sealed",
        "days_no_delete_sealed",
        "day_planning_no_insert_sealed",
        "day_planning_no_update_sealed",
        "day_planning_no_delete_sealed",
    }
    indexes = {
        row[0]
        for row in uow.conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
        )
    }
    assert indexes == {
        "idx_tasks_inventory",
        "idx_tasks_schedule",
        "idx_errands_day",
        "idx_entries_day",
        "idx_recurrence_series_state",
        "idx_recurrence_occurrence_entity",
        "idx_goal_phases_goal",
        "idx_tasks_goal",
        "idx_goals_parent",
        "idx_goal_actions_goal",
    }
    assert uow.conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[
        0
    ] == 11
    columns = {
        row[1]
        for row in uow.conn.execute("PRAGMA table_info(recurrence_series)")
    }
    assert "deleted_at" in columns
    task_columns = {row[1] for row in uow.conn.execute("PRAGMA table_info(tasks)")}
    assert {"goal_id", "phase_id"} <= task_columns
    entry_columns = {
        row[1] for row in uow.conn.execute("PRAGMA table_info(day_task_entries)")
    }
    assert {
        "goal_id_snapshot",
        "goal_title_snapshot",
        "phase_id_snapshot",
        "phase_title_snapshot",
    } <= entry_columns
    assert (
        uow.conn.execute("SELECT value FROM meta WHERE key = 'timezone'").fetchone()[0]
        == "Asia/Shanghai"
    )


def test_days_check_sealed_iff_sealed_at(uow: SqliteUnitOfWork) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        uow.conn.execute(
            "INSERT INTO days (date, status, sealed_at) VALUES ('2026-08-30', 'open', '2026-08-30T04:00:00Z')"
        )
    with pytest.raises(sqlite3.IntegrityError):
        uow.conn.execute(
            "INSERT INTO days (date, status, sealed_at) VALUES ('2026-08-30', 'sealed', NULL)"
        )
    uow.conn.execute(
        "INSERT INTO days (date, status, sealed_at) VALUES ('2026-08-30', 'open', NULL)"
    )
    uow.conn.execute(
        "INSERT INTO days (date, status, sealed_at) VALUES ('2026-08-29', 'sealed', '2026-08-30T04:00:00Z')"
    )


def test_task_completed_at_check_and_title_length(uow: SqliteUnitOfWork) -> None:
    uow.conn.execute(
        "INSERT INTO days (date, status, sealed_at) VALUES ('2026-08-30', 'open', NULL)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        uow.conn.execute(
            "INSERT INTO tasks (id, title, created_at, current_scheduled_date, completed_at, completed_on_date) "
            "VALUES ('t1', 'x', '2026-08-30T04:00:00Z', NULL, '2026-08-30T04:00:00Z', NULL)"
        )
    with pytest.raises(sqlite3.IntegrityError):
        uow.conn.execute(
            "INSERT INTO tasks (id, title, created_at, current_scheduled_date, completed_at, completed_on_date) "
            "VALUES ('t1', '', '2026-08-30T04:00:00Z', NULL, NULL, NULL)"
        )
    uow.conn.execute(
        "INSERT INTO tasks (id, title, created_at, current_scheduled_date, completed_at, completed_on_date) "
        "VALUES ('t1', 'ok', '2026-08-30T04:00:00Z', NULL, NULL, NULL)"
    )


def test_current_scheduled_date_fk_requires_days_row(uow: SqliteUnitOfWork) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        uow.conn.execute(
            "INSERT INTO tasks (id, title, created_at, current_scheduled_date, completed_at, completed_on_date) "
            "VALUES ('t1', 'x', '2026-08-30T04:00:00Z', '2026-08-30', NULL, NULL)"
        )
    uow.conn.execute(
        "INSERT INTO days (date, status, sealed_at) VALUES ('2026-08-30', 'open', NULL)"
    )
    uow.conn.execute(
        "INSERT INTO tasks (id, title, created_at, current_scheduled_date, completed_at, completed_on_date) "
        "VALUES ('t1', 'x', '2026-08-30T04:00:00Z', '2026-08-30', NULL, NULL)"
    )
    row = uow.conn.execute(
        "SELECT current_scheduled_date FROM tasks WHERE id = 't1'"
    ).fetchone()
    assert row[0] == "2026-08-30"


def test_entry_and_errand_unique_sort_order(uow: SqliteUnitOfWork) -> None:
    uow.conn.execute(
        "INSERT INTO days (date, status, sealed_at) VALUES ('2026-08-30', 'open', NULL)"
    )
    uow.conn.execute(
        "INSERT INTO tasks (id, title, created_at, current_scheduled_date, completed_at, completed_on_date) "
        "VALUES ('t1', 'a', '2026-08-30T04:00:00Z', '2026-08-30', NULL, NULL)"
    )
    uow.conn.execute(
        "INSERT INTO tasks (id, title, created_at, current_scheduled_date, completed_at, completed_on_date) "
        "VALUES ('t2', 'b', '2026-08-30T04:00:00Z', '2026-08-30', NULL, NULL)"
    )
    uow.conn.execute(
        "INSERT INTO day_task_entries (day_date, task_id, title_snapshot, sort_order, completed_on_day) "
        "VALUES ('2026-08-30', 't1', 'a', 0, 0)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        uow.conn.execute(
            "INSERT INTO day_task_entries (day_date, task_id, title_snapshot, sort_order, completed_on_day) "
            "VALUES ('2026-08-30', 't2', 'b', 0, 0)"
        )
    uow.conn.execute(
        "INSERT INTO errands (id, day_date, title, sort_order, status, completed_at) "
        "VALUES ('e1', '2026-08-30', '差事', 0, 'open', NULL)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        uow.conn.execute(
            "INSERT INTO errands (id, day_date, title, sort_order, status, completed_at) "
            "VALUES ('e2', '2026-08-30', '另一件', 0, 'open', NULL)"
        )


def test_errand_completed_at_check(uow: SqliteUnitOfWork) -> None:
    uow.conn.execute(
        "INSERT INTO days (date, status, sealed_at) VALUES ('2026-08-30', 'open', NULL)"
    )
    with pytest.raises(sqlite3.IntegrityError):
        uow.conn.execute(
            "INSERT INTO errands (id, day_date, title, sort_order, status, completed_at) "
            "VALUES ('e1', '2026-08-30', '差事', 0, 'completed', NULL)"
        )
    with pytest.raises(sqlite3.IntegrityError):
        uow.conn.execute(
            "INSERT INTO errands (id, day_date, title, sort_order, status, completed_at) "
            "VALUES ('e1', '2026-08-30', '差事', 0, 'open', '2026-08-30T04:00:00Z')"
        )
    with pytest.raises(sqlite3.IntegrityError):
        uow.conn.execute(
            "INSERT INTO errands (id, day_date, title, sort_order, status, completed_at) "
            "VALUES ('e1', '2026-08-30', '差事', 0, 'expired', '2026-08-30T04:00:00Z')"
        )
    uow.conn.execute(
        "INSERT INTO errands (id, day_date, title, sort_order, status, completed_at) "
        "VALUES ('e1', '2026-08-30', '差事', 0, 'completed', '2026-08-30T04:00:00Z')"
    )


def test_sql_statements_keeps_trigger_bodies_intact() -> None:
    script = (connection_mod.MIGRATIONS_DIR / "001_init.sql").read_text(encoding="utf-8")
    statements = connection_mod.sql_statements(script)
    triggers = [s for s in statements if s.upper().lstrip().startswith("CREATE TRIGGER")]
    assert len(triggers) == 8
    for body in triggers:
        assert "RAISE(ABORT, 'sealed day is immutable')" in body
        assert "BEGIN" in body.upper()
        assert body.rstrip().upper().endswith("END")


def test_failed_migration_rolls_back_ddl_and_version_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_args: object, **_kwargs: object) -> str:
        raise RuntimeError("injected failure")

    monkeypatch.setattr(connection_mod, "format_utc", boom)
    db_path = tmp_path / "planner.sqlite"
    with pytest.raises(RuntimeError, match="injected failure"):
        open_connection(db_path)
    probe = sqlite3.connect(str(db_path))
    try:
        tables = {
            row[0]
            for row in probe.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "days" not in tables
        assert "schema_migrations" not in tables
    finally:
        probe.close()


def test_second_open_does_not_rerun_init(db_path: Path) -> None:
    first = SqliteUnitOfWork.open(db_path)
    first.close()
    second = SqliteUnitOfWork.open(db_path)
    try:
        assert second.conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[
            0
        ] == 11
    finally:
        second.close()


def test_reopen_after_close_still_has_data(
    db_path: Path, clock: FrozenClock
) -> None:
    uow = SqliteUnitOfWork.open(db_path)
    planner = Planner(clock=clock, uow=uow)
    with uow.transaction():
        planner.add_todo_on_day(TODAY, "持久化待办")
        planner.add_to_inventory("库存项")
        planner.add_errand(TODAY, "差事")
    uow.close()

    uow2 = SqliteUnitOfWork.open(db_path)
    try:
        planner2 = Planner(clock=clock, uow=uow2)
        plan = planner2.open_day(TODAY)
        assert [e.title_snapshot for e in plan.todos] == ["持久化待办"]
        assert [e.title for e in plan.errands] == ["差事"]
        assert [item.task.title for item in planner2.list_inventory()] == ["库存项"]
    finally:
        uow2.close()


def test_domain_commands_work_through_sqlite_uow(
    uow: SqliteUnitOfWork, clock: FrozenClock
) -> None:
    planner = Planner(clock=clock, uow=uow)
    with uow.transaction():
        first = planner.add_todo_on_day(TODAY, "写完设计")
        tid = first.todos[0].task_id
        planner.add_todo_on_day(TODAY, "第二件")
        ids = [e.task_id for e in planner.open_day(TODAY).todos]
        planner.reorder_todos(TODAY, list(reversed(ids)))
        planner.complete_task_on_day(tid, TODAY)
        inv = planner.add_to_inventory("抽出")
        planner.schedule_to_date(inv.task.id, TODAY)
        planner.add_errand(TODAY, "买菜")
        planner.add_errand(TODAY, "取件")
        eids = [e.id for e in planner.open_day(TODAY).errands]
        planner.reorder_errands(TODAY, list(reversed(eids)))

    day = planner.open_day(TODAY)
    assert [e.title_snapshot for e in day.todos] == ["第二件", "写完设计", "抽出"]
    completed = next(e for e in day.todos if e.task_id == tid)
    assert completed.completed_on_day is True
    assert task_status(planner.get_task(tid)) == "completed"
    assert [e.title for e in day.errands] == ["取件", "买菜"]
    assert inv.task.id not in {item.task.id for item in planner.list_inventory()}


def test_transaction_rollback_discards_writes(
    uow: SqliteUnitOfWork, clock: FrozenClock
) -> None:
    planner = Planner(clock=clock, uow=uow)
    with pytest.raises(RuntimeError, match="boom"):
        with uow.transaction():
            planner.add_todo_on_day(TODAY, "应回滚")
            raise RuntimeError("boom")
    assert planner.open_day(TODAY).todos == []
    assert uow.get_day(TODAY) is None


def test_commands_do_not_begin_transaction(
    uow: SqliteUnitOfWork, clock: FrozenClock
) -> None:
    planner = Planner(clock=clock, uow=uow)
    planner.add_todo_on_day(TODAY, "自动提交路径")
    assert uow.conn.in_transaction is False
    with uow.transaction():
        assert uow.conn.in_transaction is True
        planner.add_todo_on_day(TODAY, "事务内")
    assert uow.conn.in_transaction is False


def test_begin_immediate_only_lives_in_uow_transaction() -> None:
    source = inspect.getsource(store_mod.SqliteUnitOfWork.transaction)
    assert "BEGIN IMMEDIATE" in source
    assert "commit" in source
    assert "rollback" in source
    for path in SRC_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(SRC_ROOT)
        if rel.parts[0] != "http":
            assert "PLANNER_LOCK" not in text, rel
        if rel.parts[0] == "persistence":
            assert "interprocess_lock" not in text, rel
            assert "fcntl" not in text, rel
        if "BEGIN IMMEDIATE" in text:
            assert rel == Path("persistence") / "store.py"
        if path.parent.name == "domain":
            assert "BEGIN IMMEDIATE" not in text
            assert "isolation_level" not in text
            assert "PLANNER_LOCK" not in text
    conn_src = inspect.getsource(connection_mod)
    assert "BEGIN IMMEDIATE" not in conn_src
    assert ".executescript" not in inspect.getsource(connection_mod.apply_migrations)


def test_same_task_second_open_schedule_conflicts(
    uow: SqliteUnitOfWork, clock: FrozenClock
) -> None:
    planner = Planner(clock=clock, uow=uow)
    with uow.transaction():
        plan = planner.add_todo_on_day(TODAY, "单排期")
        tid = plan.todos[0].task_id
        with pytest.raises(Conflict, match="两天"):
            uow.save_entry(
                DayTaskEntry(
                    day_date="2026-08-31",
                    task_id=tid,
                    title_snapshot="单排期",
                    sort_order=0,
                    completed_on_day=False,
                )
            )
