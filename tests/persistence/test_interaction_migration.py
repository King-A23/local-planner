import sqlite3
from contextlib import closing

import pytest

from local_planner.persistence import SqliteUnitOfWork
from local_planner.persistence.connection import MIGRATIONS_DIR, sql_statements


def test_v6_upgrade_keeps_history_and_creates_recoverable_backup(tmp_path):
    path = tmp_path / "planner.sqlite"
    with closing(sqlite3.connect(path)) as conn:
        for file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            version = int(file.name.split("_")[0])
            if version > 6:
                break
            for statement in sql_statements(file.read_text()):
                conn.execute(statement)
            conn.execute("INSERT INTO schema_migrations VALUES (?, '2026-08-29T00:00:00Z')", (version,))
        conn.execute("INSERT INTO days VALUES ('2026-08-29','open',NULL)")
        conn.execute("INSERT INTO tasks(id,title,created_at) VALUES ('task','旧事项','2026-08-29T00:00:00Z')")
        conn.execute("INSERT INTO day_task_entries(day_date,task_id,title_snapshot,sort_order,completed_on_day) VALUES ('2026-08-29','task','旧快照',0,0)")
        conn.execute("UPDATE days SET status='sealed',sealed_at='2026-08-30T00:00:00Z'")
        conn.commit()
    store = SqliteUnitOfWork.open(path)
    try:
        assert store.get_task("task").notes == ""
        assert store.get_entry("2026-08-29", "task").title_snapshot == "旧快照"
        assert store.get_entry("2026-08-29", "task").notes_snapshot == ""
        assert store.get_day("2026-08-29").manual_todo_order is False
        with pytest.raises(sqlite3.IntegrityError, match="sealed"):
            store.conn.execute("UPDATE day_task_entries SET notes_snapshot='改动'")
        with pytest.raises(sqlite3.IntegrityError, match="sealed"):
            store.conn.execute("UPDATE days SET manual_todo_order=1")
        backup = next((tmp_path / "backups").glob("pre-migrate-7-*.sqlite"))
        with closing(sqlite3.connect(backup)) as conn:
            assert conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 6
            assert conn.execute("SELECT title_snapshot FROM day_task_entries").fetchone()[0] == "旧快照"
    finally:
        store.close()
