"""Domain types. CalendarDate is an Asia/Shanghai civil YYYY-MM-DD string."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal, Optional

from local_planner.domain.errors import ValidationError

CalendarDate = str  # "2026-08-30"
UtcInstant = str  # "2026-08-30T16:01:00Z"
TaskId = str
ErrandId = str

TaskStatus = Literal["inventory", "scheduled", "completed"]
ErrandStatus = Literal["open", "completed", "expired"]
DayStatus = Literal["open", "sealed"]
RecurrenceKind = Literal["plan", "errand"]
RecurrenceFrequency = Literal["daily", "weekly"]
RecurrenceState = Literal["active", "paused", "stopped"]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TITLE_MAX = 200


def parse_calendar_date(value: str) -> date:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise ValidationError("日期格式无效")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError("日期格式无效") from None


def add_calendar_days(d: CalendarDate, n: int) -> CalendarDate:
    return (parse_calendar_date(d) + timedelta(days=n)).isoformat()


def day_before(d: CalendarDate) -> CalendarDate:
    return add_calendar_days(d, -1)


def check_year_cap(target: CalendarDate, today: CalendarDate) -> None:
    if abs(parse_calendar_date(target).year - parse_calendar_date(today).year) > 10:
        raise ValidationError("日期距今超过 10 年")


def normalize_title(title: str) -> str:
    if not isinstance(title, str):
        raise ValidationError("标题不能为空")
    stripped = title.strip()
    if not stripped:
        raise ValidationError("标题不能为空")
    if len(stripped) > TITLE_MAX:
        raise ValidationError("标题最长 200 字")
    return stripped


def normalize_notes(notes: str) -> str:
    if not isinstance(notes, str) or len(notes) > 10000:
        raise ValidationError("备注最长 10000 字")
    return notes.replace("\r\n", "\n").replace("\r", "\n")


@dataclass(frozen=True)
class Task:
    id: TaskId
    title: str
    created_at: UtcInstant
    current_scheduled_date: Optional[CalendarDate]
    completed_at: Optional[UtcInstant]
    completed_on_date: Optional[CalendarDate]
    target_date: Optional[CalendarDate] = None
    discarded_at: Optional[UtcInstant] = None
    series_id: Optional[str] = None
    occurrence_date: Optional[CalendarDate] = None
    notes: str = ""
    goal_id: str | None = None
    phase_id: str | None = None


@dataclass(frozen=True)
class DayTaskEntry:
    """A task's appearance on one day. Sealed/past days must not update this snapshot."""

    day_date: CalendarDate
    task_id: TaskId
    title_snapshot: str
    sort_order: int
    completed_on_day: bool
    start_clock: Optional[str] = None
    end_clock: Optional[str] = None
    series_id: Optional[str] = None
    occurrence_date: Optional[CalendarDate] = None
    notes_snapshot: str = ""
    goal_id_snapshot: str | None = None
    goal_title_snapshot: str | None = None
    phase_id_snapshot: str | None = None
    phase_title_snapshot: str | None = None


@dataclass(frozen=True)
class Errand:
    id: ErrandId
    day_date: CalendarDate
    title: str
    sort_order: int
    status: ErrandStatus
    completed_at: Optional[UtcInstant]
    start_clock: Optional[str] = None
    end_clock: Optional[str] = None
    series_id: Optional[str] = None
    occurrence_date: Optional[CalendarDate] = None
    notes: str = ""


@dataclass(frozen=True)
class DayRecord:
    date: CalendarDate
    status: DayStatus
    sealed_at: Optional[UtcInstant]
    manual_todo_order: bool = False
    manual_errand_order: bool = False


@dataclass(frozen=True)
class DayPlan:
    date: CalendarDate
    status: DayStatus
    sealed_at: Optional[UtcInstant]
    todos: list[DayTaskEntry]
    errands: list[Errand]
    manual_todo_order: bool = False
    manual_errand_order: bool = False


@dataclass(frozen=True)
class InventoryItem:
    task: Task


@dataclass(frozen=True)
class RecurrenceSeries:
    id: str
    kind: RecurrenceKind
    title: str
    frequency: RecurrenceFrequency
    weekdays_mask: int
    start_date: CalendarDate
    schedule_from: CalendarDate
    default_start_clock: Optional[str]
    default_end_clock: Optional[str]
    state: RecurrenceState
    created_at: UtcInstant
    updated_at: UtcInstant
    paused_at: Optional[UtcInstant]
    stopped_at: Optional[UtcInstant]
    deleted_at: Optional[UtcInstant]


@dataclass(frozen=True)
class RecurrenceOccurrence:
    series_id: str
    occurrence_date: CalendarDate
    kind: RecurrenceKind
    entity_id: Optional[str]
    disposition: Literal["materialized", "skipped_sealed"]
    generated_at: UtcInstant


@dataclass(frozen=True)
class UpcomingDay:
    date: CalendarDate
    todo_count: int
    errand_count: int
    recurrence_count: int


@dataclass(frozen=True)
class PlanningView:
    date: CalendarDate
    status: Literal["unplanned", "ready"]
    planned_at: Optional[UtcInstant]
    day: DayPlan
    returned_from_yesterday: list[InventoryItem]
    due: list[InventoryItem]
    inventory: list[InventoryItem]
    upcoming: list[UpcomingDay]


def task_status(t: Task) -> TaskStatus:
    if t.completed_at is not None:
        return "completed"
    if t.current_scheduled_date is not None:
        return "scheduled"
    return "inventory"


def is_writable(day: DayPlan, today: CalendarDate) -> bool:
    return day.date >= today and day.status == "open"


@dataclass(frozen=True)
class Goal:
    id: str
    title: str
    notes: str
    horizon_text: str
    state: Literal["active", "paused", "ended"]
    end_reason: Literal["achieved", "abandoned"] | None
    next_task_id: str | None
    focus_phase_id: str | None
    revision: int
    created_at: str
    updated_at: str
    ended_at: str | None = None


@dataclass(frozen=True)
class GoalPhase:
    id: str
    goal_id: str
    title: str
    notes: str
    position: int
    status: Literal["open", "done", "skipped"] = "open"
