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
    RecurrenceOccurrence,
    RecurrenceSeries,
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
            "SELECT t.id, t.title, t.created_at, t.current_scheduled_date, "
            "t.completed_at, t.completed_on_date, t.target_date, t.discarded_at, t.notes, "
            "ro.series_id AS recurrence_series_id, "
            "ro.occurrence_date AS recurrence_occurrence_date "
            "FROM tasks t LEFT JOIN recurrence_occurrences ro "
            "ON ro.kind = 'plan' AND ro.entity_id = t.id WHERE t.id = ?",
            (task_id,),
        ).fetchone()
        return None if row is None else _task_from_row(row)

    def save_task(self, task: Task) -> None:
        self.conn.execute(
            """
            INSERT INTO tasks (
              id, title, created_at, current_scheduled_date,
              completed_at, completed_on_date, target_date, discarded_at, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              title = excluded.title,
              created_at = excluded.created_at,
              current_scheduled_date = excluded.current_scheduled_date,
              completed_at = excluded.completed_at,
              completed_on_date = excluded.completed_on_date,
              target_date = excluded.target_date,
              discarded_at = excluded.discarded_at,
              notes = excluded.notes
            """,
            (
                task.id,
                task.title,
                task.created_at,
                task.current_scheduled_date,
                task.completed_at,
                task.completed_on_date,
                task.target_date,
                task.discarded_at,
                task.notes,
            ),
        )

    def delete_task_row(self, task_id: TaskId) -> None:
        self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))

    def get_day(self, d: CalendarDate) -> DayRecord | None:
        row = self.conn.execute(
            "SELECT date, status, sealed_at, manual_todo_order, manual_errand_order FROM days WHERE date = ?",
            (d,),
        ).fetchone()
        return None if row is None else _day_from_row(row)

    def save_day(self, day: DayRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO days (date, status, sealed_at, manual_todo_order, manual_errand_order) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
              status = excluded.status,
              sealed_at = excluded.sealed_at,
              manual_todo_order = excluded.manual_todo_order,
              manual_errand_order = excluded.manual_errand_order
            """,
            (day.date, day.status, day.sealed_at, day.manual_todo_order, day.manual_errand_order),
        )

    def get_entry(self, day: CalendarDate, task_id: TaskId) -> DayTaskEntry | None:
        row = self.conn.execute(
            "SELECT e.day_date, e.task_id, e.title_snapshot, e.notes_snapshot, e.sort_order, "
            "e.completed_on_day, e.start_clock, e.end_clock, "
            "ro.series_id AS recurrence_series_id, "
            "ro.occurrence_date AS recurrence_occurrence_date "
            "FROM day_task_entries e LEFT JOIN recurrence_occurrences ro "
            "ON ro.kind = 'plan' AND ro.entity_id = e.task_id "
            "WHERE e.day_date = ? AND e.task_id = ?",
            (day, task_id),
        ).fetchone()
        return None if row is None else _entry_from_row(row)

    def list_entries(self, day: CalendarDate) -> list[DayTaskEntry]:
        rows = self.conn.execute(
            "SELECT e.day_date, e.task_id, e.title_snapshot, e.notes_snapshot, e.sort_order, "
            "e.completed_on_day, e.start_clock, e.end_clock, "
            "ro.series_id AS recurrence_series_id, "
            "ro.occurrence_date AS recurrence_occurrence_date "
            "FROM day_task_entries e LEFT JOIN recurrence_occurrences ro "
            "ON ro.kind = 'plan' AND ro.entity_id = e.task_id "
            "WHERE e.day_date = ? ORDER BY e.sort_order",
            (day,),
        ).fetchall()
        return [_entry_from_row(row) for row in rows]

    def list_entries_for_task(self, task_id: TaskId) -> list[DayTaskEntry]:
        rows = self.conn.execute(
            "SELECT e.day_date, e.task_id, e.title_snapshot, e.notes_snapshot, e.sort_order, "
            "e.completed_on_day, e.start_clock, e.end_clock, "
            "ro.series_id AS recurrence_series_id, "
            "ro.occurrence_date AS recurrence_occurrence_date "
            "FROM day_task_entries e LEFT JOIN recurrence_occurrences ro "
            "ON ro.kind = 'plan' AND ro.entity_id = e.task_id "
            "WHERE e.task_id = ? ORDER BY e.day_date, e.sort_order",
            (task_id,),
        ).fetchall()
        return [_entry_from_row(row) for row in rows]

    def save_entry(self, entry: DayTaskEntry) -> None:
        reject_second_open_schedule(self, entry)
        self.conn.execute(
            """
            INSERT INTO day_task_entries (
              day_date, task_id, title_snapshot, sort_order, completed_on_day,
              start_clock, end_clock, notes_snapshot
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(day_date, task_id) DO UPDATE SET
              title_snapshot = excluded.title_snapshot,
              sort_order = excluded.sort_order,
              completed_on_day = excluded.completed_on_day,
              start_clock = excluded.start_clock,
              end_clock = excluded.end_clock,
              notes_snapshot = excluded.notes_snapshot
            """,
            (
                entry.day_date,
                entry.task_id,
                entry.title_snapshot,
                entry.sort_order,
                1 if entry.completed_on_day else 0,
                entry.start_clock,
                entry.end_clock,
                entry.notes_snapshot,
            ),
        )

    def delete_entry(self, day: CalendarDate, task_id: TaskId) -> None:
        self.conn.execute(
            "DELETE FROM day_task_entries WHERE day_date = ? AND task_id = ?",
            (day, task_id),
        )

    def get_errand(self, errand_id: ErrandId) -> Errand | None:
        row = self.conn.execute(
            "SELECT e.id, e.day_date, e.title, e.notes, e.sort_order, e.status, "
            "e.completed_at, e.start_clock, e.end_clock, "
            "ro.series_id AS recurrence_series_id, "
            "ro.occurrence_date AS recurrence_occurrence_date "
            "FROM errands e LEFT JOIN recurrence_occurrences ro "
            "ON ro.kind = 'errand' AND ro.entity_id = e.id WHERE e.id = ?",
            (errand_id,),
        ).fetchone()
        return None if row is None else _errand_from_row(row)

    def list_errands(self, day: CalendarDate) -> list[Errand]:
        rows = self.conn.execute(
            "SELECT e.id, e.day_date, e.title, e.notes, e.sort_order, e.status, "
            "e.completed_at, e.start_clock, e.end_clock, "
            "ro.series_id AS recurrence_series_id, "
            "ro.occurrence_date AS recurrence_occurrence_date "
            "FROM errands e LEFT JOIN recurrence_occurrences ro "
            "ON ro.kind = 'errand' AND ro.entity_id = e.id "
            "WHERE e.day_date = ? ORDER BY e.sort_order",
            (day,),
        ).fetchall()
        return [_errand_from_row(row) for row in rows]

    def save_errand(self, errand: Errand) -> None:
        self.conn.execute(
            """
            INSERT INTO errands (
              id, day_date, title, sort_order, status, completed_at,
              start_clock, end_clock, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              day_date = excluded.day_date,
              title = excluded.title,
              sort_order = excluded.sort_order,
              status = excluded.status,
              completed_at = excluded.completed_at,
              start_clock = excluded.start_clock,
              end_clock = excluded.end_clock,
              notes = excluded.notes
            """,
            (
                errand.id,
                errand.day_date,
                errand.title,
                errand.sort_order,
                errand.status,
                errand.completed_at,
                errand.start_clock,
                errand.end_clock,
                errand.notes,
            ),
        )

    def delete_errand(self, errand_id: ErrandId) -> None:
        self.conn.execute("DELETE FROM errands WHERE id = ?", (errand_id,))

    def list_inventory_tasks(self) -> list[Task]:
        rows = self.conn.execute(
            """
            SELECT t.id, t.title, t.created_at, t.current_scheduled_date,
                   t.completed_at, t.completed_on_date, t.target_date, t.discarded_at, t.notes,
                   ro.series_id AS recurrence_series_id,
                   ro.occurrence_date AS recurrence_occurrence_date
            FROM tasks t
            LEFT JOIN recurrence_occurrences ro
              ON ro.kind = 'plan' AND ro.entity_id = t.id
            WHERE t.completed_at IS NULL AND t.current_scheduled_date IS NULL
              AND t.discarded_at IS NULL
            ORDER BY t.created_at DESC, t.rowid DESC
            """
        ).fetchall()
        return [_task_from_row(row) for row in rows]

    def list_scheduled_after(self, today: CalendarDate) -> list[Task]:
        rows = self.conn.execute(
            """
            SELECT t.id, t.title, t.created_at, t.current_scheduled_date,
                   t.completed_at, t.completed_on_date, t.target_date, t.discarded_at, t.notes,
                   ro.series_id AS recurrence_series_id,
                   ro.occurrence_date AS recurrence_occurrence_date
            FROM tasks t
            LEFT JOIN recurrence_occurrences ro
              ON ro.kind = 'plan' AND ro.entity_id = t.id
            WHERE t.completed_at IS NULL
              AND t.current_scheduled_date IS NOT NULL
              AND t.current_scheduled_date > ?
            ORDER BY t.current_scheduled_date ASC, t.title ASC
            """,
            (today,),
        ).fetchall()
        return [_task_from_row(row) for row in rows]

    def list_errands_after(self, today: CalendarDate) -> list[Errand]:
        rows = self.conn.execute(
            """
            SELECT e.id, e.day_date, e.title, e.notes, e.sort_order, e.status,
                   e.completed_at, e.start_clock, e.end_clock,
                   ro.series_id AS recurrence_series_id,
                   ro.occurrence_date AS recurrence_occurrence_date
            FROM errands e
            LEFT JOIN recurrence_occurrences ro
              ON ro.kind = 'errand' AND ro.entity_id = e.id
            WHERE e.day_date > ?
            ORDER BY e.day_date, e.sort_order, e.id
            """,
            (today,),
        ).fetchall()
        return [_errand_from_row(row) for row in rows]

    def get_recurrence(self, series_id: str) -> RecurrenceSeries | None:
        row = self.conn.execute(
            "SELECT * FROM recurrence_series WHERE id = ?", (series_id,)
        ).fetchone()
        return None if row is None else _recurrence_from_row(row)

    def list_recurrences(self) -> list[RecurrenceSeries]:
        rows = self.conn.execute(
            """
            SELECT * FROM recurrence_series
            WHERE deleted_at IS NULL
            ORDER BY CASE state WHEN 'active' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END,
                     created_at, id
            """
        ).fetchall()
        return [_recurrence_from_row(row) for row in rows]

    def save_recurrence(self, series: RecurrenceSeries) -> None:
        self.conn.execute(
            """
            INSERT INTO recurrence_series (
              id, kind, title, frequency, weekdays_mask, start_date, schedule_from,
              default_start_clock, default_end_clock, state, created_at, updated_at,
              paused_at, stopped_at, deleted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              kind = excluded.kind,
              title = excluded.title,
              frequency = excluded.frequency,
              weekdays_mask = excluded.weekdays_mask,
              start_date = excluded.start_date,
              schedule_from = excluded.schedule_from,
              default_start_clock = excluded.default_start_clock,
              default_end_clock = excluded.default_end_clock,
              state = excluded.state,
              created_at = excluded.created_at,
              updated_at = excluded.updated_at,
              paused_at = excluded.paused_at,
              stopped_at = excluded.stopped_at,
              deleted_at = excluded.deleted_at
            """,
            (
                series.id,
                series.kind,
                series.title,
                series.frequency,
                series.weekdays_mask,
                series.start_date,
                series.schedule_from,
                series.default_start_clock,
                series.default_end_clock,
                series.state,
                series.created_at,
                series.updated_at,
                series.paused_at,
                series.stopped_at,
                series.deleted_at,
            ),
        )

    def get_occurrence(
        self, series_id: str, occurrence_date: CalendarDate
    ) -> RecurrenceOccurrence | None:
        row = self.conn.execute(
            """
            SELECT series_id, occurrence_date, kind, entity_id, disposition, generated_at
            FROM recurrence_occurrences
            WHERE series_id = ? AND occurrence_date = ?
            """,
            (series_id, occurrence_date),
        ).fetchone()
        return None if row is None else _occurrence_from_row(row)

    def save_occurrence(self, occurrence: RecurrenceOccurrence) -> None:
        self.conn.execute(
            """
            INSERT INTO recurrence_occurrences (
              series_id, occurrence_date, kind, entity_id, disposition, generated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(series_id, occurrence_date) DO NOTHING
            """,
            (
                occurrence.series_id,
                occurrence.occurrence_date,
                occurrence.kind,
                occurrence.entity_id,
                occurrence.disposition,
                occurrence.generated_at,
            ),
        )

    def get_planned_at(self, day: CalendarDate) -> str | None:
        row = self.conn.execute(
            "SELECT planned_at FROM day_planning WHERE day_date = ?", (day,)
        ).fetchone()
        return None if row is None else row["planned_at"]

    def set_day_planned(self, day: CalendarDate, planned_at: str) -> None:
        self.conn.execute(
            """
            INSERT INTO day_planning (day_date, planned_at) VALUES (?, ?)
            ON CONFLICT(day_date) DO UPDATE SET planned_at = excluded.planned_at
            """,
            (day, planned_at),
        )

    def is_proven_empty(self) -> bool:
        for table in ("days", "day_task_entries", "errands", "recurrence_series"):
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
              UNION ALL
              SELECT schedule_from FROM recurrence_series
              WHERE deleted_at IS NULL
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
        notes=row["notes"],
        created_at=row["created_at"],
        current_scheduled_date=row["current_scheduled_date"],
        completed_at=row["completed_at"],
        completed_on_date=row["completed_on_date"],
        target_date=row["target_date"] if "target_date" in row.keys() else None,
        discarded_at=row["discarded_at"] if "discarded_at" in row.keys() else None,
        series_id=(
            row["recurrence_series_id"]
            if "recurrence_series_id" in row.keys()
            else None
        ),
        occurrence_date=(
            row["recurrence_occurrence_date"]
            if "recurrence_occurrence_date" in row.keys()
            else None
        ),
    )


def _day_from_row(row: sqlite3.Row) -> DayRecord:
    return DayRecord(
        date=row["date"],
        status=row["status"],
        sealed_at=row["sealed_at"],
        manual_todo_order=bool(row["manual_todo_order"]),
        manual_errand_order=bool(row["manual_errand_order"]),
    )


def _entry_from_row(row: sqlite3.Row) -> DayTaskEntry:
    return DayTaskEntry(
        day_date=row["day_date"],
        task_id=row["task_id"],
        title_snapshot=row["title_snapshot"],
        notes_snapshot=row["notes_snapshot"],
        sort_order=int(row["sort_order"]),
        completed_on_day=bool(row["completed_on_day"]),
        start_clock=row["start_clock"] if "start_clock" in row.keys() else None,
        end_clock=row["end_clock"] if "end_clock" in row.keys() else None,
        series_id=(
            row["recurrence_series_id"]
            if "recurrence_series_id" in row.keys()
            else None
        ),
        occurrence_date=(
            row["recurrence_occurrence_date"]
            if "recurrence_occurrence_date" in row.keys()
            else None
        ),
    )


def _errand_from_row(row: sqlite3.Row) -> Errand:
    return Errand(
        id=row["id"],
        day_date=row["day_date"],
        title=row["title"],
        notes=row["notes"],
        sort_order=int(row["sort_order"]),
        status=row["status"],
        completed_at=row["completed_at"],
        start_clock=row["start_clock"] if "start_clock" in row.keys() else None,
        end_clock=row["end_clock"] if "end_clock" in row.keys() else None,
        series_id=(
            row["recurrence_series_id"]
            if "recurrence_series_id" in row.keys()
            else None
        ),
        occurrence_date=(
            row["recurrence_occurrence_date"]
            if "recurrence_occurrence_date" in row.keys()
            else None
        ),
    )


def _recurrence_from_row(row: sqlite3.Row) -> RecurrenceSeries:
    return RecurrenceSeries(
        id=row["id"],
        kind=row["kind"],
        title=row["title"],
        frequency=row["frequency"],
        weekdays_mask=int(row["weekdays_mask"]),
        start_date=row["start_date"],
        schedule_from=row["schedule_from"],
        default_start_clock=row["default_start_clock"],
        default_end_clock=row["default_end_clock"],
        state=row["state"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        paused_at=row["paused_at"],
        stopped_at=row["stopped_at"],
        deleted_at=row["deleted_at"] if "deleted_at" in row.keys() else None,
    )


def _occurrence_from_row(row: sqlite3.Row) -> RecurrenceOccurrence:
    return RecurrenceOccurrence(
        series_id=row["series_id"],
        occurrence_date=row["occurrence_date"],
        kind=row["kind"],
        entity_id=row["entity_id"],
        disposition=row["disposition"],
        generated_at=row["generated_at"],
    )
