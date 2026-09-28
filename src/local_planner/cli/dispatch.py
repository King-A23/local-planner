"""Parse domain argv, run under exclusive_uow + planner_txn, print JSON envelope."""

from __future__ import annotations

import logging
import sys
import time
import traceback
from typing import Any

from local_planner.cli.envelope import (
    UsageError,
    dump_envelope,
    failure,
    success,
)
from local_planner.cli.parser import build_domain_parser
from local_planner.domain import commands as cmds
from local_planner.domain.commands import UNSET
from local_planner.domain.recurrence import UNSET as RECURRENCE_UNSET
from local_planner.domain.errors import DaySealed, DomainError
from local_planner.domain.models import add_calendar_days, parse_calendar_date
from local_planner.domain.search import search_items
from local_planner.agent_contract import capabilities_payload
from local_planner.paths import data_dir, db_path, resolve_clock
from local_planner.present import (
    calendar_payload,
    command_payload,
    context_payload,
    day_plan_payload,
    meta_payload,
    recurrence_payload,
)
from local_planner.runtime import (
    InternalError,
    LockTimeout,
    configure_logging,
    exclusive_uow,
    planner_txn,
)

logger = logging.getLogger(__name__)


def _resolve_date(token: str, today: str) -> str:
    if token == "today":
        return today
    if token == "tomorrow":
        return add_calendar_days(today, 1)
    return parse_calendar_date(token).isoformat()


def _weekdays(value: str | None) -> list[str] | None:
    if value is None:
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def _human_line(command: str, today: str, data: dict[str, Any]) -> str:
    if command == "context":
        return (
            f"今天 {today} "
            f"{'可写' if data.get('writable') else '只读'} · "
            f"Plan {len(data.get('todos') or [])} · "
            f"Errands {len(data.get('errands') or [])} · "
            f"To Do {data.get('inventoryCount', 0)} · "
            f"未来已排 {len(data.get('scheduledAhead') or [])}"
        )
    if "todos" in data:
        return (
            f"今天 {today} · {data.get('date', '')} "
            f"{'可写' if data.get('writable') else '只读'} · "
            f"Plan {len(data.get('todos') or [])} · "
            f"Errands {len(data.get('errands') or [])}"
        )
    if "items" in data:
        return f"今天 {today} · To Do {len(data.get('items') or [])}"
    if "inventoryCount" in data:
        return f"今天 {today} · To Do {data.get('inventoryCount')}"
    return f"今天 {today} · {command}"


def _run(args: Any, today: str, clock: Any, uow: Any) -> dict[str, Any]:
    command = args.envelope_command
    if command == "meta":
        return meta_payload(uow, today)
    if command == "capabilities":
        return capabilities_payload()
    if command == "search":
        return search_items(clock, uow, args.query)
    if command == "context":
        return context_payload(clock, uow, today)
    if command == "calendar":
        return calendar_payload(
            uow, _resolve_date(args.date_from, today), _resolve_date(args.date_to, today), today
        )
    if command == "day.open":
        return day_plan_payload(
            cmds.open_day(clock, uow, _resolve_date(args.date, today)), today
        )
    if command == "day.todo.add":
        return day_plan_payload(
            cmds.add_todo_on_day(
                clock,
                uow,
                _resolve_date(args.date, today),
                args.title,
                getattr(args, "start_clock", None),
                getattr(args, "end_clock", None),
            ),
            today,
        )
    if command == "day.todo.complete":
        return day_plan_payload(
            cmds.complete_task_on_day(
                clock, uow, args.task_id, _resolve_date(args.date, today)
            ),
            today,
        )
    if command == "day.todo.uncomplete":
        return day_plan_payload(
            cmds.uncomplete_task_on_day(
                clock, uow, args.task_id, _resolve_date(args.date, today)
            ),
            today,
        )
    if command == "day.todo.reorder":
        date = _resolve_date(args.date, today)
        ids = args.task_ids
        if args.automatic:
            if ids:
                raise UsageError("--automatic 不能同时指定事项 ID", command=command)
            ids = [item.task_id for item in cmds.open_day(clock, uow, date).todos]
        return day_plan_payload(
            cmds.reorder_todos(clock, uow, date, ids, manual=not args.automatic),
            today,
        )
    if command == "day.errand.add":
        return day_plan_payload(
            cmds.add_errand(
                clock,
                uow,
                _resolve_date(args.date, today),
                args.title,
                getattr(args, "start_clock", None),
                getattr(args, "end_clock", None),
            ),
            today,
        )
    if command == "day.errand.reorder":
        date = _resolve_date(args.date, today)
        ids = args.errand_ids
        if args.automatic:
            if ids:
                raise UsageError("--automatic 不能同时指定事项 ID", command=command)
            ids = [item.id for item in cmds.open_day(clock, uow, date).errands]
        return day_plan_payload(
            cmds.reorder_errands(
                clock, uow, date, ids, manual=not args.automatic
            ),
            today,
        )
    if command == "inventory.list":
        items = cmds.list_inventory(uow)
        from local_planner.present import inventory_item_payload

        return {"items": [inventory_item_payload(item) for item in items]}
    if command == "inventory.add":
        target = getattr(args, "target_date", None)
        if target:
            target = _resolve_date(target, today)
        return command_payload(
            cmds.add_to_inventory(clock, uow, args.title, target),
            today,
        )
    if command == "inventory.complete":
        return day_plan_payload(cmds.complete_inventory_task(clock, uow, args.task_id), today)
    if command in ("task.edit", "errand.edit"):
        if not (hasattr(args, "title") or hasattr(args, "notes") or args.clear_notes):
            raise UsageError("至少提供 --title、--notes 或 --clear-notes", command=command)
        kind = "task" if command == "task.edit" else "errand"
        return command_payload(cmds.edit_details(
            clock, uow, kind, getattr(args, f"{kind}_id"),
            getattr(args, "title", args.expected_title),
            "" if args.clear_notes else getattr(args, "notes", args.expected_notes),
            args.expected_title, args.expected_notes,
        ), today)
    if command == "recurrence.list":
        return {
            "items": [
                recurrence_payload(item, today)
                for item in cmds.list_recurrences(uow)
            ]
        }
    if command == "recurrence.add":
        return recurrence_payload(
            cmds.create_recurrence(
                clock,
                uow,
                kind=args.kind,
                title=args.title,
                frequency=args.frequency,
                weekdays=_weekdays(args.weekdays),
                start_date=_resolve_date(args.start_date, today),
                default_start_clock=args.start_clock,
                default_end_clock=args.end_clock,
            ),
            today,
        )
    if command == "recurrence.update":
        if args.clear_start and hasattr(args, "start_clock"):
            raise UsageError("--start 与 --clear-start 不能同时使用", command=command)
        if args.clear_end and hasattr(args, "end_clock"):
            raise UsageError("--end 与 --clear-end 不能同时使用", command=command)
        changed = any(
            hasattr(args, name)
            for name in ("title", "frequency", "weekdays", "start_date", "start_clock", "end_clock")
        ) or args.clear_start or args.clear_end
        if not changed:
            raise UsageError("至少提供一项修改", command=command)
        return recurrence_payload(
            cmds.update_recurrence(
                clock,
                uow,
                args.series_id,
                title=getattr(args, "title", RECURRENCE_UNSET),
                frequency=getattr(args, "frequency", RECURRENCE_UNSET),
                weekdays=(
                    _weekdays(args.weekdays)
                    if hasattr(args, "weekdays")
                    else RECURRENCE_UNSET
                ),
                start_date=(
                    _resolve_date(args.start_date, today)
                    if hasattr(args, "start_date")
                    else RECURRENCE_UNSET
                ),
                default_start_clock=(
                    None
                    if args.clear_start
                    else getattr(args, "start_clock", RECURRENCE_UNSET)
                ),
                default_end_clock=(
                    None
                    if args.clear_end
                    else getattr(args, "end_clock", RECURRENCE_UNSET)
                ),
            ),
            today,
        )
    if command == "recurrence.pause":
        return recurrence_payload(
            cmds.pause_recurrence(clock, uow, args.series_id), today
        )
    if command == "recurrence.resume":
        return recurrence_payload(
            cmds.resume_recurrence(clock, uow, args.series_id), today
        )
    if command == "recurrence.stop":
        return recurrence_payload(
            cmds.stop_recurrence(clock, uow, args.series_id), today
        )
    if command == "recurrence.delete":
        cmds.delete_recurrence(clock, uow, args.series_id)
        return {"ok": True}
    if command == "task.schedule":
        return day_plan_payload(
            cmds.schedule_to_date(
                clock, uow, args.task_id, _resolve_date(args.date, today)
            ),
            today,
        )
    if command == "task.unschedule":
        return command_payload(cmds.unschedule(clock, uow, args.task_id), today)
    if command == "task.rename":
        return command_payload(cmds.rename_task(clock, uow, args.task_id, args.title), today)
    if command == "task.delete":
        cmds.delete_task(clock, uow, args.task_id)
        return command_payload(None, today)
    if command == "errand.complete":
        return day_plan_payload(cmds.complete_errand(clock, uow, args.errand_id), today)
    if command == "errand.uncomplete":
        return day_plan_payload(cmds.uncomplete_errand(clock, uow, args.errand_id), today)
    if command == "errand.rename":
        return day_plan_payload(
            cmds.rename_errand(clock, uow, args.errand_id, args.title), today
        )
    if command == "errand.delete":
        return day_plan_payload(cmds.delete_errand(clock, uow, args.errand_id), today)
    if command == "task.target":
        raw = None if args.clear else args.target_date
        if raw:
            raw = _resolve_date(raw, today)
        return command_payload(
            cmds.set_target_date(clock, uow, args.task_id, raw), today
        )
    if command == "day.todo.time":
        start = getattr(args, "start_clock", UNSET)
        end = getattr(args, "end_clock", UNSET)
        if start is UNSET and end is UNSET:
            start = end = None
        return day_plan_payload(
            cmds.set_plan_clocks(
                clock,
                uow,
                _resolve_date(args.date, today),
                args.task_id,
                start,
                end,
            ),
            today,
        )
    if command == "errand.time":
        start = getattr(args, "start_clock", UNSET)
        end = getattr(args, "end_clock", UNSET)
        if start is UNSET and end is UNSET:
            start = end = None
        return day_plan_payload(
            cmds.set_errand_clocks(clock, uow, args.errand_id, start, end),
            today,
        )
    raise UsageError("未知命令", command=command)


def dispatch_domain(argv: list[str]) -> int:
    configure_logging()
    pretty = False
    parser = build_domain_parser()
    txn_today: str | None = None
    command: str | None = None
    started = time.monotonic()
    try:
        args = parser.parse_args(argv)
        pretty = bool(args.pretty)
        command = args.envelope_command
        clock = resolve_clock()
        with exclusive_uow(data_dir(), db_path()) as uow:
            with planner_txn(clock, uow) as today:
                txn_today = today
                data = _run(args, today, clock, uow)
        payload = success(command or "unknown", txn_today, data)
        dump_envelope(payload, pretty=pretty)
        if args.human:
            print(_human_line(command or "", txn_today, data), file=sys.stderr)
        ms = int((time.monotonic() - started) * 1000)
        logger.info("cli command=%s ok=true ms=%s", command, ms)
        return 0
    except UsageError as exc:
        dump_envelope(
            failure(exc.command, exc.code, exc.message),
            pretty=pretty,
        )
        logger.info("cli command=%s ok=false code=UsageError ms=%s", exc.command, 0)
        return 2
    except LockTimeout as exc:
        dump_envelope(
            failure(command, exc.code, exc.message),
            pretty=pretty,
        )
        logger.info("cli command=%s ok=false code=LockTimeout wait_s=15", command)
        return 3
    except DomainError as exc:
        date = getattr(exc, "date", None)
        dump_envelope(
            failure(command, exc.code, exc.message, today=txn_today, date=date),
            pretty=pretty,
        )
        logger.info(
            "cli command=%s ok=false code=%s date=%s",
            command,
            exc.code,
            date or "",
        )
        return 1
    except InternalError as exc:
        dump_envelope(
            failure(command, exc.code, exc.message, today=txn_today),
            pretty=pretty,
        )
        traceback.print_exc()
        return 4
    except SystemExit:
        raise
    except Exception as exc:
        dump_envelope(
            failure(
                command,
                "InternalError",
                "内部错误",
                today=txn_today,
            ),
            pretty=pretty,
        )
        traceback.print_exc()
        logger.exception("cli command=%s ok=false code=InternalError", command)
        return 4
