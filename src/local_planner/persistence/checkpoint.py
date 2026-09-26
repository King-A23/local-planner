"""SQLite backup snapshots for undoing the last agent run."""

from __future__ import annotations

import sqlite3
from pathlib import Path

CHECKPOINT_NAME = "agent-checkpoint.sqlite"


def checkpoint_path(data_dir: Path) -> Path:
    return data_dir / CHECKPOINT_NAME


def snapshot_connection(conn: sqlite3.Connection, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    for extra in (dest, Path(f"{dest}-wal"), Path(f"{dest}-shm")):
        extra.unlink(missing_ok=True)
    snap = sqlite3.connect(str(dest))
    try:
        conn.backup(snap)
    finally:
        snap.close()


def restore_connection(conn: sqlite3.Connection, src: Path) -> None:
    snap = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        snap.backup(conn)
    finally:
        snap.close()
