"""CLI backup uses the SQLite backup API (WAL-safe), not a raw file copy."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from local_planner.__main__ import main
from local_planner.backup import backup
from local_planner.clock import FrozenClock
from local_planner.domain.commands import Planner
from local_planner.persistence import SqliteUnitOfWork

TODAY = "2026-08-30"
FROZEN = "2026-08-30T12:00:00+08:00"


def _seed(db: Path) -> None:
    uow = SqliteUnitOfWork.open(db)
    planner = Planner(clock=FrozenClock(FROZEN), uow=uow)
    with uow.transaction():
        planner.add_todo_on_day(TODAY, "备份这一条")
    # leave the connection open until the caller closes — WAL may be present
    uow.close()


def test_backup_cli_default_dir(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("LOCAL_PLANNER_DATA_DIR", str(tmp_path))
    _seed(tmp_path / "planner.sqlite")
    assert main(["backup"]) == 0
    out = capsys.readouterr().out
    backups = list((tmp_path / "backups").glob("planner-*.sqlite"))
    assert len(backups) == 1
    dest = backups[0]
    assert str(dest) in out
    titles = [
        row[0]
        for row in sqlite3.connect(dest).execute("SELECT title FROM tasks")
    ]
    assert titles == ["备份这一条"]


def test_backup_while_source_is_open(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_PLANNER_DATA_DIR", str(tmp_path))
    db = tmp_path / "planner.sqlite"
    uow = SqliteUnitOfWork.open(db)
    planner = Planner(clock=FrozenClock(FROZEN), uow=uow)
    with uow.transaction():
        planner.add_todo_on_day(TODAY, "还开着")
    dest = backup()
    try:
        probe = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
        titles = [row[0] for row in probe.execute("SELECT title FROM tasks")]
        probe.close()
        assert titles == ["还开着"]
    finally:
        uow.close()


def test_backup_to_user_path_and_directory(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("LOCAL_PLANNER_DATA_DIR", str(tmp_path))
    _seed(tmp_path / "planner.sqlite")
    file_dest = tmp_path / "out" / "copy.sqlite"
    assert main(["backup", str(file_dest)]) == 0
    assert file_dest.exists()
    assert "已备份到" in capsys.readouterr().out
    dir_dest = tmp_path / "copies"
    dir_dest.mkdir()
    assert main(["backup", str(dir_dest)]) == 0
    copies = list(dir_dest.glob("planner-*.sqlite"))
    assert len(copies) == 1


def test_backup_refuses_missing_db_and_overwrite(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    monkeypatch.setenv("LOCAL_PLANNER_DATA_DIR", str(tmp_path))
    assert main(["backup"]) == 1
    err = capsys.readouterr().err
    assert "找不到数据库" in err
    _seed(tmp_path / "planner.sqlite")
    dest = tmp_path / "exists.sqlite"
    dest.write_bytes(b"x")
    assert main(["backup", str(dest)]) == 1
    assert "目标已存在" in capsys.readouterr().err
    assert dest.read_bytes() == b"x"


def test_backup_too_many_args(capsys) -> None:
    assert main(["backup", "a", "b"]) == 1
    assert "用法" in capsys.readouterr().err
