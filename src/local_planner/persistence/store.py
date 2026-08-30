"""SQLite UnitOfWork. Domain commands must not BEGIN; only transaction() does."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from local_planner.domain.models import (
    CalendarDate,
    DayRecord,
    DayTaskEntry,
    Errand,
    ErrandId,
    Task,
    TaskId,
)
from local_planner.domain.store import reject_second_open_schedule
from local_planner.persistence.connection import open_connection


class SqliteMeta:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key = ?",
            (key,),
        ).fetchone()
        return None if row is None else row["value"]

    def set(self, key: str, value: str) -> None:
        self._conn.execute(
            """
            INSERT INTO meta (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )


class SqliteUnitOfWork:
    """File-backed store implementing the domain UnitOfWork port."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.meta = SqliteMeta(conn)

    @classmethod
    def open(cls, path: str | Path) -> SqliteUnitOfWork:
        return cls(open_connection(path))

    def close(self) -> None:
        self.conn.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Process-wide unique BEGIN/COMMIT/ROLLBACK for this connection."""
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def get_task(self, task_id: TaskId) -> Task | None:
        row = self.conn.execute(
            "SELECT id, title, created_at, current_scheduled_date, "
            "completed_at, completed_on_date FROM tasks WHERE id = ?",
            (task_id,),
        ).fetchone()
        return None if row is None else _task_from_row(row)

    def save_task(self, task: Task) -> None:
        self.conn.execute(
            """
            INSERT INTO tasks (
              id, title, created_at, current_scheduled_date,
              completed_at, completed_on_date
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              title = excluded.title,
              created_at = excluded.created_at,
              current_scheduled_date = excluded.current_scheduled_date,
              completed_at = excluded.completed_at,
              completed_on_date = excluded.completed_on_date
            """,
            (
                task.id,
                task.title,
                task.created_at,
                task.current_scheduled_date,
                task.completed_at,
                task.completed_on_date,
            ),
        )

    def delete_task_row(self, task_id: TaskId) -> None:
        self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    def get_day(self, d: CalendarDate) -> DayRecord | None:
        row = self.conn.execute(
            "SELECT date, status, sealed_at FROM days WHERE date = ?",
            (d,),
        ).fetchone()
        return None if row is None else _day_from_row(row)

    def save_day(self, day: DayRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO days (date, status, sealed_at) VALUES (?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
              status = excluded.status,
              sealed_at = excluded.sealed_at
            """,
            (day.date, day.status, day.sealed_at),
        )

    def get_entry(self, day: CalendarDate, task_id: TaskId) -> DayTaskEntry | None:
        row = self.conn.execute(
            "SELECT day_date, task_id, title_snapshot, sort_order, completed_on_day "
            "FROM day_task_entries WHERE day_date = ? AND task_id = ?",
            (day, task_id),
        ).fetchone()
        return None if row is None else _entry_from_row(row)

    def list_entries(self, day: CalendarDate) -> list[DayTaskEntry]:
        rows = self.conn.execute(
            "SELECT day_date, task_id, title_snapshot, sort_order, completed_on_day "
            "FROM day_task_entries WHERE day_date = ? ORDER BY sort_order",
            (day,),
        ).fetchall()
        return [_entry_from_row(row) for row in rows]

    def list_entries_for_task(self, task_id: TaskId) -> list[DayTaskEntry]:
        rows = self.conn.execute(
            "SELECT day_date, task_id, title_snapshot, sort_order, completed_on_day "
            "FROM day_task_entries WHERE task_id = ? ORDER BY day_date, sort_order",
            (task_id,),
        ).fetchall()
        return [_entry_from_row(row) for row in rows]

    def save_entry(self, entry: DayTaskEntry) -> None:
        reject_second_open_schedule(self, entry)
        self.conn.execute(
            """
            INSERT INTO day_task_entries (
              day_date, task_id, title_snapshot, sort_order, completed_on_day
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(day_date, task_id) DO UPDATE SET
              title_snapshot = excluded.title_snapshot,
              sort_order = excluded.sort_order,
              completed_on_day = excluded.completed_on_day
            """,
            (
                entry.day_date,
                entry.task_id,
                entry.title_snapshot,
                entry.sort_order,
                1 if entry.completed_on_day else 0,
            ),
        )

    def delete_entry(self, day: CalendarDate, task_id: TaskId) -> None:
        self.conn.execute(
            "DELETE FROM day_task_entries WHERE day_date = ? AND task_id = ?",
            (day, task_id),
        )

    def get_errand(self, errand_id: ErrandId) -> Errand | None:
        row = self.conn.execute(
            "SELECT id, day_date, title, sort_order, status, completed_at "
            "FROM errands WHERE id = ?",
            (errand_id,),
        ).fetchone()
        return None if row is None else _errand_from_row(row)

    def list_errands(self, day: CalendarDate) -> list[Errand]:
        rows = self.conn.execute(
            "SELECT id, day_date, title, sort_order, status, completed_at "
            "FROM errands WHERE day_date = ? ORDER BY sort_order",
            (day,),
        ).fetchall()
        return [_errand_from_row(row) for row in rows]

    def save_errand(self, errand: Errand) -> None:
        self.conn.execute(
            """
            INSERT INTO errands (
              id, day_date, title, sort_order, status, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              day_date = excluded.day_date,
              title = excluded.title,
              sort_order = excluded.sort_order,
              status = excluded.status,
              completed_at = excluded.completed_at
            """,
            (
                errand.id,
                errand.day_date,
                errand.title,
                errand.sort_order,
                errand.status,
                errand.completed_at,
            ),
        )

    def delete_errand(self, errand_id: ErrandId) -> None:
        self.conn.execute("DELETE FROM errands WHERE id = ?", (errand_id,))

    def list_inventory_tasks(self) -> list[Task]:
        rows = self.conn.execute(
            """
            SELECT id, title, created_at, current_scheduled_date,
                   completed_at, completed_on_date
            FROM tasks
            WHERE completed_at IS NULL AND current_scheduled_date IS NULL
            ORDER BY created_at DESC, rowid DESC
            """
        ).fetchall()
        return [_task_from_row(row) for row in rows]

    def is_proven_empty(self) -> bool:
        for table in ("days", "day_task_entries", "errands"):
            row = self.conn.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
            if row is not None:
                return False
        return True

    def earliest_relevant_date(self) -> CalendarDate | None:
        row = self.conn.execute(
            """
            SELECT MIN(d) FROM (
              SELECT date AS d FROM days
              UNION ALL
              SELECT day_date FROM day_task_entries
              UNION ALL
              SELECT day_date FROM errands
              UNION ALL
              SELECT current_scheduled_date FROM tasks
              WHERE current_scheduled_date IS NOT NULL
            )
            """
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return row[0]


def _task_from_row(row: sqlite3.Row) -> Task:
    return Task(
        id=row["id"],
        title=row["title"],
        created_at=row["created_at"],
        current_scheduled_date=row["current_scheduled_date"],
        completed_at=row["completed_at"],
        completed_on_date=row["completed_on_date"],
    )


def _day_from_row(row: sqlite3.Row) -> DayRecord:
    return DayRecord(
        date=row["date"],
        status=row["status"],
        sealed_at=row["sealed_at"],
    )


def _entry_from_row(row: sqlite3.Row) -> DayTaskEntry:
    return DayTaskEntry(
        day_date=row["day_date"],
        task_id=row["task_id"],
        title_snapshot=row["title_snapshot"],
        sort_order=int(row["sort_order"]),
        completed_on_day=bool(row["completed_on_day"]),
    )


def _errand_from_row(row: sqlite3.Row) -> Errand:
    return Errand(
        id=row["id"],
        day_date=row["day_date"],
        title=row["title"],
        sort_order=int(row["sort_order"]),
        status=row["status"],
        completed_at=row["completed_at"],
    )
