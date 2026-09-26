"""Local snapshots and validated in-place recovery. Callers own planner locks."""

from __future__ import annotations

import logging
import re
import sqlite3
from contextlib import closing
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from local_planner.clock import Clock, SHANGHAI
from local_planner.domain.errors import NotFound, ValidationError
from local_planner.persistence.connection import MIGRATIONS_DIR, copy_sqlite, sql_statements
from local_planner.persistence import SqliteUnitOfWork

MAX_BACKUP_BYTES = 32 * 1024 * 1024
AUTO_KEEP = 14
_NAME = re.compile(r"^[a-zA-Z0-9_-]+\.sqlite$")
logger = logging.getLogger(__name__)


def backup_path(root: Path, name: str) -> Path:
    folder = (root / "backups").resolve()
    candidate = folder / name
    if not _NAME.fullmatch(name) or candidate.is_symlink() or not candidate.is_file():
        raise NotFound("找不到这份备份")
    return candidate


def snapshot(conn: sqlite3.Connection, root: Path, kind: str = "manual") -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    name = f"{kind}-{stamp}-{uuid.uuid4().hex[:8]}.sqlite"
    dest = root / "backups" / name
    temp = dest.with_suffix(".partial")
    try:
        copy_sqlite(conn, temp)
        temp.replace(dest)
    finally:
        temp.unlink(missing_ok=True)
    return backup_info(dest)


def backup_info(path: Path) -> dict:
    name = path.name
    kind = "migration" if name.startswith("pre-migrate-") else "auto" if name.startswith("auto-") else "before-restore" if name.startswith("before-restore-") else "imported" if name.startswith("imported-") else "manual"
    return {"name": name, "kind": kind, "createdLabel": datetime.fromtimestamp(path.stat().st_mtime, SHANGHAI).strftime("%Y年%m月%d日 %H:%M"), "createdAt": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(), "bytes": path.stat().st_size}


def list_backups(root: Path) -> list[dict]:
    paths = [p for p in (root / "backups").glob("*.sqlite") if not p.is_symlink() and p.is_file() and _NAME.fullmatch(p.name)]
    return [backup_info(p) for p in sorted(paths, key=lambda p: p.stat().st_mtime, reverse=True)]


def ensure_daily_backup(conn: sqlite3.Connection, root: Path, today: str) -> None:
    """One snapshot per Shanghai day. Prune only our daily automatic snapshots."""
    dest = root / "backups" / f"auto-{today}.sqlite"
    if dest.exists():
        return
    temp = dest.with_suffix(".partial")
    try:
        copy_sqlite(conn, temp)
        temp.replace(dest)
        daily = sorted((root / "backups").glob("auto-????-??-??.sqlite"), reverse=True)
        for old in daily[AUTO_KEEP:]:
            if not old.is_symlink():
                old.unlink(missing_ok=True)
    finally:
        temp.unlink(missing_ok=True)


def _schema(conn: sqlite3.Connection) -> list[tuple]:
    return [tuple(row) for row in conn.execute("SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name")]


def validate_backup(path: Path) -> None:
    """Accept only our known schema, before running any migrations on imported data."""
    if path.stat().st_size > MAX_BACKUP_BYTES:
        raise ValidationError("备份文件不能超过 32 MB")
    try:
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as conn:
            conn.execute("PRAGMA trusted_schema=OFF")
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or conn.execute("PRAGMA foreign_key_check").fetchone():
                raise ValidationError("备份文件不完整，请选择另一份备份")
            versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]
            files = sorted(MIGRATIONS_DIR.glob("[0-9]*.sql"))
            known = [int(p.name.split("_")[0]) for p in files]
            if not versions or versions != known[:len(versions)]:
                raise ValidationError("备份版本不兼容，请使用对应版本的 Local Planner")
            with closing(sqlite3.connect(":memory:")) as expected:
                for file in files[:len(versions)]:
                    for statement in sql_statements(file.read_text(encoding="utf-8")):
                        expected.execute(statement)
                if _schema(conn) != _schema(expected):
                    raise ValidationError("这不是兼容的 Local Planner 备份")
            if conn.execute("SELECT value FROM meta WHERE key='timezone'").fetchone() != ("Asia/Shanghai",):
                raise ValidationError("备份的日期设置不兼容")
    except sqlite3.Error as exc:
        raise ValidationError("无法读取备份，请选择有效的 Local Planner 备份文件") from exc


def restore(conn: sqlite3.Connection, root: Path, source: Path, clock: Clock) -> dict:
    from local_planner.runtime import planner_txn

    validate_backup(source)
    # Migrate and settle a temporary copy first, so invalid data cannot replace live data.
    with tempfile.TemporaryDirectory(prefix="planner-restore-", dir=root) as folder:
        stage = Path(folder) / "planner.sqlite"
        with closing(sqlite3.connect(f"{source.resolve().as_uri()}?mode=ro", uri=True)) as src:
            copy_sqlite(src, stage)
        staged = SqliteUnitOfWork.open(stage)
        try:
            with planner_txn(clock, staged):
                staged.meta.set("recovery_generation", str(uuid.uuid4()))
            if staged.conn.execute("PRAGMA foreign_key_check").fetchone():
                raise ValidationError("备份中的数据不完整，未恢复")
            previous = snapshot(conn, root, "before-restore")
            staged.conn.backup(conn)
            return {"ok": True, "safetyBackup": previous}
        finally:
            staged.close()
