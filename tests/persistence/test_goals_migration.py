"""Compatibility checks for the long-term goal schema migration."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from local_planner.persistence import SqliteUnitOfWork
from local_planner.persistence.connection import MIGRATIONS_DIR


def test_open_refuses_unknown_future_schema_without_mutating_database(
    tmp_path: Path,
) -> None:
    """An old app must fail closed instead of applying its own migrations."""
    path = tmp_path / "planner.sqlite"
    store = SqliteUnitOfWork.open(path)
    try:
        store.conn.execute("INSERT INTO meta(key, value) VALUES ('marker', 'keep')")
    finally:
        store.close()

    with closing(sqlite3.connect(path)) as conn:
        conn.execute(
            "INSERT INTO schema_migrations(version, applied_at) VALUES (999, 'future')"
        )
        conn.commit()

    with pytest.raises(sqlite3.DatabaseError, match="数据库版本不兼容"):
        SqliteUnitOfWork.open(path)

    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT value FROM meta WHERE key = 'marker'").fetchone() == (
            "keep",
        )
        assert [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")][-1] == 999


def test_goal_schema_migration_is_present() -> None:
    """The compatibility suite requires the dedicated long-term goals migration."""
    assert (MIGRATIONS_DIR / "008_goals.sql").is_file()
