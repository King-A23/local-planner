"""SQLite connection, pragmas, and schema migrations.

SqliteUnitOfWork.transaction() owns command-path txn begin/commit/rollback.
apply_migrations uses a one-shot BEGIN at open so DDL and the version row
commit together. It must not call executescript (that issues COMMIT).
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from local_planner.clock import format_utc

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_MIGRATION_NAME = re.compile(r"^(\d+)_.+\.sql$")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def open_connection(path: str | Path) -> sqlite3.Connection:
    """Open planner.sqlite with isolation_level=None (SQLite autocommit).

    That disables Python's implicit BEGIN DEFERRED so the only explicit
    user transaction is SqliteUnitOfWork.transaction().
    """
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
    try:
        apply_migrations(conn, data_dir=db_path.parent)
        _seed_timezone(conn)
        _require_integrity(conn)
        return conn
    except Exception:
        conn.close()
        raise


def apply_migrations(conn: sqlite3.Connection, data_dir: Path) -> None:
    """Apply numbered 00N_*.sql files; version truth is schema_migrations only."""
    migrations = _migration_files()
    applied = _applied_versions(conn, [version for version, _ in migrations])
    existing_database = bool(applied)
    for version, sql_path in migrations:
        if version in applied:
            continue
        if existing_database:
            _backup_before_migrate(conn, data_dir, version)
        statements = sql_statements(sql_path.read_text(encoding="utf-8"))
        # Open-time exception to UoW-only txns: DDL + version row must be atomic.
        conn.execute("BEGIN")
        try:
            for statement in statements:
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                (version, format_utc(datetime.now(timezone.utc))),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied.add(version)


def sql_statements(script: str) -> list[str]:
    """Split a migration script. CREATE TRIGGER bodies stay one statement."""
    statements: list[str] = []
    n = len(script)
    i = 0
    start = 0
    trigger_header = False
    trigger_body = False
    body_stmt_start = False

    def skip_leading() -> None:
        nonlocal i, start
        i = _skip_comment_or_space(script, i)
        start = i

    skip_leading()
    while i < n:
        if script.startswith("--", i):
            nl = script.find("\n", i)
            i = n if nl < 0 else nl + 1
            continue
        if script.startswith("/*", i):
            end = script.find("*/", i + 2)
            if end < 0:
                raise ValueError("unclosed block comment in migration")
            i = end + 2
            continue
        if script[i] in ("'", '"'):
            if trigger_body and body_stmt_start:
                body_stmt_start = False
            i = _skip_string(script, i)
            continue

        ident = _IDENT.match(script, i)
        if ident:
            word = ident.group(0).upper()
            if not trigger_header and not trigger_body and word == "CREATE":
                j = _skip_comment_or_space(script, ident.end())
                nxt = _IDENT.match(script, j)
                if nxt is not None and nxt.group(0).upper() == "TRIGGER":
                    trigger_header = True
            elif trigger_header and word == "BEGIN":
                trigger_header = False
                trigger_body = True
                body_stmt_start = True
                i = ident.end()
                continue
            elif trigger_body and body_stmt_start and word == "END":
                i = ident.end()
                i = _skip_comment_or_space(script, i)
                if i < n and script[i] == ";":
                    i += 1
                stmt = script[start:i].strip().rstrip(";").strip()
                if stmt:
                    statements.append(stmt)
                trigger_body = False
                body_stmt_start = False
                skip_leading()
                continue
            elif trigger_body and body_stmt_start:
                body_stmt_start = False
            i = ident.end()
            continue

        if script[i] == ";":
            if trigger_body:
                body_stmt_start = True
                i += 1
                continue
            stmt = script[start:i].strip()
            if stmt:
                statements.append(stmt)
            i += 1
            skip_leading()
            continue

        if trigger_body and body_stmt_start and not script[i].isspace():
            body_stmt_start = False
        i += 1

    tail = script[start:i].strip().rstrip(";").strip()
    if tail:
        statements.append(tail)
    return statements


def _skip_comment_or_space(script: str, i: int) -> int:
    n = len(script)
    while i < n:
        if script[i].isspace():
            i += 1
            continue
        if script.startswith("--", i):
            nl = script.find("\n", i)
            i = n if nl < 0 else nl + 1
            continue
        if script.startswith("/*", i):
            end = script.find("*/", i + 2)
            if end < 0:
                raise ValueError("unclosed block comment in migration")
            i = end + 2
            continue
        break
    return i


def _skip_string(script: str, i: int) -> int:
    quote = script[i]
    i += 1
    n = len(script)
    while i < n:
        if script[i] == quote:
            if i + 1 < n and script[i + 1] == quote:
                i += 2
                continue
            return i + 1
        i += 1
    raise ValueError("unclosed string in migration")


def _migration_files() -> list[tuple[int, Path]]:
    found: list[tuple[int, Path]] = []
    for path in MIGRATIONS_DIR.glob("*.sql"):
        match = _MIGRATION_NAME.match(path.name)
        if match is None:
            raise ValueError(f"migration filename must be NNN_name.sql: {path.name}")
        found.append((int(match.group(1)), path))
    found.sort(key=lambda item: item[0])
    return found


def _applied_versions(
    conn: sqlite3.Connection, known_versions: list[int] | None = None
) -> set[int]:
    """Return a verified, prefix-shaped schema migration history.

    A newer application may migrate an older database, but an older application
    must never open a database that already contains a migration it does not
    know.  Checking this before any backup, DDL, or meta write keeps a failed
    downgrade attempt read-only.
    """
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).fetchone()
    if row is None:
        return set()
    versions = [int(r[0]) for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
    if not versions:
        raise sqlite3.DatabaseError("数据库迁移记录不完整，无法安全打开")
    expected = known_versions
    if expected is None:
        expected = [version for version, _ in _migration_files()]
    if versions != expected[: len(versions)]:
        raise sqlite3.DatabaseError(
            "数据库版本不兼容，请使用创建它的较新版本 Local Planner"
        )
    return set(versions)


def copy_sqlite(source_conn: sqlite3.Connection, dest: Path) -> None:
    """WAL-safe snapshot via sqlite3 backup API (not a raw file copy)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    backup_conn = sqlite3.connect(str(dest))
    try:
        source_conn.backup(backup_conn)
    except Exception:
        backup_conn.close()
        dest.unlink(missing_ok=True)
        raise
    backup_conn.close()


def backup_sqlite_file(source: Path, dest: Path) -> Path:
    """Copy planner.sqlite with the backup API so a live WAL is included."""
    source = source.expanduser().resolve()
    dest = dest.expanduser()
    if not source.exists():
        raise FileNotFoundError(source)
    if dest.exists():
        raise FileExistsError(dest)
    dest = dest.resolve()
    if dest == source:
        raise ValueError("不能备份到源文件")
    src = sqlite3.connect(
        str(source),
        isolation_level=None,
        check_same_thread=False,
    )
    try:
        src.execute("PRAGMA busy_timeout = 5000")
        copy_sqlite(src, dest)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    finally:
        src.close()
    return dest


def _backup_before_migrate(
    conn: sqlite3.Connection, data_dir: Path, version: int
) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = data_dir / "backups" / f"pre-migrate-{version}-{stamp}.sqlite"
    copy_sqlite(conn, dest)


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
