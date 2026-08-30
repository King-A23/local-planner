"""SQLite connection, pragmas, and schema migrations.

BEGIN/COMMIT/ROLLBACK must not appear here — only UnitOfWork.transaction().
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from local_planner.clock import format_utc

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_MIGRATION_NAME = re.compile(r"^(\d+)_.+\.sql$")


def open_connection(path: str | Path) -> sqlite3.Connection:
    """Open planner.sqlite with autocommit off Python's implicit BEGIN DEFERRED."""
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(db_path),
        isolation_level=None,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    apply_migrations(conn, data_dir=db_path.parent)
    _seed_timezone(conn)
    _require_integrity(conn)
    return conn


def apply_migrations(conn: sqlite3.Connection, data_dir: Path) -> None:
    """Apply numbered 00N_*.sql files; version truth is schema_migrations only."""
    applied = _applied_versions(conn)
    for version, sql_path in _migration_files():
        if version in applied:
            continue
        if applied:
            _backup_before_migrate(conn, data_dir, version)
        script = sql_path.read_text(encoding="utf-8")
        conn.executescript(script)
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (version, format_utc(datetime.now(timezone.utc))),
        )
        applied.add(version)


def _migration_files() -> list[tuple[int, Path]]:
    found: list[tuple[int, Path]] = []
    for path in MIGRATIONS_DIR.glob("*.sql"):
        match = _MIGRATION_NAME.match(path.name)
        if match is None:
            raise ValueError(f"migration filename must be NNN_name.sql: {path.name}")
        found.append((int(match.group(1)), path))
    found.sort(key=lambda item: item[0])
    return found


def _applied_versions(conn: sqlite3.Connection) -> set[int]:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    if row is None:
        return set()
    return {int(r[0]) for r in conn.execute("SELECT version FROM schema_migrations")}


def _backup_before_migrate(
    conn: sqlite3.Connection, data_dir: Path, version: int
) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = data_dir / "backups" / f"pre-migrate-{version}-{stamp}.sqlite"
    dest.parent.mkdir(parents=True, exist_ok=True)
    backup_conn = sqlite3.connect(dest)
    try:
        conn.backup(backup_conn)
    finally:
        backup_conn.close()


def _seed_timezone(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)",
        ("timezone", "Asia/Shanghai"),
    )


def _require_integrity(conn: sqlite3.Connection) -> None:
    result = conn.execute("PRAGMA integrity_check").fetchone()
    if result is None or result[0] != "ok":
        raise sqlite3.DatabaseError(
            f"integrity_check failed: {None if result is None else result[0]}"
        )
