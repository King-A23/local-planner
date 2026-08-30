"""Data directory, sqlite path, and injectable clock. Shared by serve, backup, CLI."""

from __future__ import annotations

import os
from pathlib import Path

from local_planner.clock import Clock, FrozenClock, SystemClock

DB_NAME = "planner.sqlite"


def data_dir() -> Path:
    override = os.environ.get("LOCAL_PLANNER_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if os.environ.get("LOCAL_PLANNER_DEV") == "1":
        return Path(__file__).resolve().parents[2] / ".data"
    return Path.home() / "Library" / "Application Support" / "local-planner"


def db_path() -> Path:
    return data_dir() / DB_NAME


def resolve_clock() -> Clock:
    pinned = os.environ.get("LOCAL_PLANNER_CLOCK")
    allowed = os.environ.get("LOCAL_PLANNER_ALLOW_CLOCK_OVERRIDE") == "1"
    if pinned and allowed:
        return FrozenClock(pinned)
    return SystemClock()
