"""WAL-safe copy of planner.sqlite via the SQLite backup API."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from local_planner.paths import data_dir, db_path
from local_planner.persistence.connection import backup_sqlite_file
from local_planner.runtime import interprocess_lock


def default_backup_name() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"planner-{stamp}.sqlite"


def resolve_backup_dest(path: str | None) -> Path:
    if path is None:
        return data_dir() / "backups" / default_backup_name()
    dest = Path(path).expanduser()
    if dest.exists() and dest.is_dir():
        return dest / default_backup_name()
    return dest


def backup(path: str | None = None) -> Path:
    with interprocess_lock(data_dir()):
        return backup_sqlite_file(db_path(), resolve_backup_dest(path))
