"""Long-term goal data remains safe across backup and recovery."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from local_planner.clock import FrozenClock
from local_planner.domain import planning
from local_planner.domain.errors import Conflict
from local_planner.persistence import SqliteUnitOfWork
from local_planner.persistence.connection import MIGRATIONS_DIR, sql_statements
from local_planner.recovery import restore, snapshot


CLOCK = FrozenClock("2026-08-30T12:00:00+08:00")


def _create_database_at_v7(path: Path) -> None:
    with closing(sqlite3.connect(path)) as conn:
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = int(migration.name.split("_", 1)[0])
            if version > 7:
                break
            for statement in sql_statements(migration.read_text(encoding="utf-8")):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, '2026-08-30T00:00:00Z')",
                (version,),
            )
        conn.execute("INSERT INTO meta(key, value) VALUES ('timezone', 'Asia/Shanghai')")
        conn.execute("INSERT INTO days(date, status, sealed_at) VALUES ('2026-08-30', 'open', NULL)")
        conn.execute(
            "INSERT INTO tasks(id, title, created_at) VALUES ('old-task', '旧待办', '2026-08-30T00:00:00Z')"
        )
        conn.execute(
            """
            INSERT INTO day_task_entries(day_date, task_id, title_snapshot, sort_order, completed_on_day)
            VALUES ('2026-08-30', 'old-task', '旧快照', 0, 0)
            """
        )
        conn.commit()


def test_v7_backup_restores_and_migrates_goal_fields_to_null(tmp_path: Path) -> None:
    backups = tmp_path / "backups"
    backups.mkdir()
    old_backup = backups / "legacy-v7.sqlite"
    _create_database_at_v7(old_backup)

    live = SqliteUnitOfWork.open(tmp_path / "planner.sqlite")
    try:
        result = restore(live.conn, tmp_path, old_backup, CLOCK)
        assert result["ok"] is True
        assert live.conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 11
        assert tuple(
            live.conn.execute("SELECT goal_id, phase_id FROM tasks WHERE id = 'old-task'").fetchone()
        ) == (None, None)
        assert tuple(live.conn.execute(
            """
            SELECT goal_id_snapshot, goal_title_snapshot, phase_id_snapshot, phase_title_snapshot
            FROM day_task_entries WHERE task_id = 'old-task'
            """
        ).fetchone()) == (None, None, None, None)
    finally:
        live.close()


def test_goal_phase_task_and_day_snapshots_round_trip_through_restore(tmp_path: Path) -> None:
    live = SqliteUnitOfWork.open(tmp_path / "planner.sqlite")
    try:
        live.conn.execute("INSERT INTO days(date, status, sealed_at) VALUES ('2026-08-30', 'open', NULL)")
        live.conn.execute(
            """
            INSERT INTO goals(
              id, title, notes, horizon_text, state, end_reason, next_task_id, focus_phase_id,
              revision, created_at, updated_at, ended_at
            ) VALUES ('goal-1', '通过 CSP', '按阶段练习', '明年', 'active', NULL, NULL, NULL,
                      3, '2026-08-30T00:00:00Z', '2026-08-30T00:00:00Z', NULL)
            """
        )
        live.conn.execute(
            """
            INSERT INTO goal_phases(id, goal_id, title, notes, position, status)
            VALUES ('phase-1', 'goal-1', '基础', '完成两套模拟题', 0, 'open')
            """
        )
        live.conn.execute(
            """
            INSERT INTO tasks(id, title, created_at, current_scheduled_date, notes, goal_id, phase_id)
            VALUES ('task-1', '做一套模拟题', '2026-08-30T00:00:00Z', '2026-08-30', '记录错题',
                    'goal-1', 'phase-1')
            """
        )
        live.conn.execute(
            "UPDATE goals SET next_task_id = 'task-1', focus_phase_id = 'phase-1' WHERE id = 'goal-1'"
        )
        live.conn.execute(
            "INSERT INTO goal_requests(request_id, fingerprint, goal_id) VALUES ('request-1', 'fingerprint', 'goal-1')"
        )
        live.conn.execute(
            """
            INSERT INTO day_task_entries(
              day_date, task_id, title_snapshot, notes_snapshot, sort_order, completed_on_day,
              goal_id_snapshot, goal_title_snapshot, phase_id_snapshot, phase_title_snapshot
            ) VALUES ('2026-08-30', 'task-1', '做一套模拟题', '记录错题', 0, 0,
                      'goal-1', '通过 CSP', 'phase-1', '基础')
            """
        )
        saved = snapshot(live.conn, tmp_path)

        live.conn.execute("UPDATE goals SET title = '不应保留' WHERE id = 'goal-1'")
        live.conn.execute("UPDATE goal_phases SET title = '不应保留' WHERE id = 'phase-1'")
        live.conn.execute("UPDATE tasks SET notes = '不应保留' WHERE id = 'task-1'")
        live.conn.execute("UPDATE day_task_entries SET goal_title_snapshot = '不应保留' WHERE task_id = 'task-1'")

        result = restore(live.conn, tmp_path, tmp_path / "backups" / saved["name"], CLOCK)
        assert result["ok"] is True
        assert tuple(live.conn.execute(
            """
            SELECT title, notes, horizon_text, state, next_task_id, focus_phase_id, revision
            FROM goals WHERE id = 'goal-1'
            """
        ).fetchone()) == ("通过 CSP", "按阶段练习", "明年", "active", "task-1", "phase-1", 3)
        assert tuple(live.conn.execute(
            "SELECT goal_id, title, notes, position, status FROM goal_phases WHERE id = 'phase-1'"
        ).fetchone()) == ("goal-1", "基础", "完成两套模拟题", 0, "open")
        assert tuple(live.conn.execute(
            "SELECT title, notes, goal_id, phase_id FROM tasks WHERE id = 'task-1'"
        ).fetchone()) == ("做一套模拟题", "记录错题", "goal-1", "phase-1")
        assert tuple(live.conn.execute(
            "SELECT fingerprint, goal_id FROM goal_requests WHERE request_id = 'request-1'"
        ).fetchone()) == ("fingerprint", "goal-1")
        assert tuple(live.conn.execute(
            """
            SELECT title_snapshot, notes_snapshot, goal_id_snapshot, goal_title_snapshot,
                   phase_id_snapshot, phase_title_snapshot
            FROM day_task_entries WHERE day_date = '2026-08-30' AND task_id = 'task-1'
            """
        ).fetchone()) == ("做一套模拟题", "记录错题", "goal-1", "通过 CSP", "phase-1", "基础")
    finally:
        live.close()


def test_planning_draft_survives_restore_but_old_generation_cannot_write(tmp_path: Path) -> None:
    (tmp_path / "backups").mkdir()
    live = SqliteUnitOfWork.open(tmp_path / "planner.sqlite")
    try:
        with live.transaction():
            draft = planning.create_draft(
                CLOCK, live, request_id="draft-before-restore", recovery_generation=None,
            )
        saved = snapshot(live.conn, tmp_path)
        result = restore(live.conn, tmp_path, tmp_path / "backups" / saved["name"], CLOCK)
        assert result["ok"] is True
        restored = planning.get_draft(live, draft["id"])
        assert restored["id"] == draft["id"]
        assert restored["recoveryGeneration"] is None
        with live.transaction(), pytest.raises(Conflict, match="数据已恢复"):
            planning.change_draft(
                CLOCK, live, draft["id"], "discard", expected_revision=restored["revision"],
                recovery_generation=None, request_id="old-generation-write",
            )
    finally:
        live.close()
