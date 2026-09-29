"""Domain argv parser. Process commands (serve/backup) are not parsed here."""

from __future__ import annotations

import argparse

from local_planner.cli.envelope import UsageError


class DomainParser(argparse.ArgumentParser):
    def __init__(self, *args: object, envelope_command: str | None = None, **kwargs: object) -> None:
        kwargs.setdefault("add_help", True)
        super().__init__(*args, **kwargs)
        self.envelope_command = envelope_command

    def error(self, message: str) -> None:
        raise UsageError(message, command=self.envelope_command)

    def exit(self, status: int = 0, message: str | None = None) -> None:
        if status == 0:
            raise SystemExit(0)
        raise UsageError(
            (message or "").strip() or "用法错误",
            command=self.envelope_command,
        )


def _leaf(sub: argparse._SubParsersAction[DomainParser], name: str, envelope: str) -> DomainParser:
    parser = sub.add_parser(name, envelope_command=envelope)
    parser.envelope_command = envelope
    parser.set_defaults(envelope_command=envelope)
    return parser


def _edit(sub: argparse._SubParsersAction[DomainParser], kind: str) -> None:
    edit = _leaf(sub, "edit", f"{kind}.edit")
    edit.add_argument(f"{kind}_id")
    edit.add_argument("--title", default=argparse.SUPPRESS)
    notes = edit.add_mutually_exclusive_group()
    notes.add_argument("--notes", default=argparse.SUPPRESS, help="替换完整备注；多行文本需作为一个参数")
    notes.add_argument("--clear-notes", action="store_true")
    edit.add_argument("--expected-title", required=True, help="最近读取的原始标题，用于冲突检查")
    edit.add_argument("--expected-notes", required=True, help="最近读取的原始备注；空备注传空字符串")


def _move(sub: argparse._SubParsersAction[DomainParser], kind: str) -> None:
    move = _leaf(sub, "move", f"day.{kind}.move")
    move.add_argument("date")
    move.add_argument("item_id")
    target = move.add_mutually_exclusive_group(required=True)
    target.add_argument("--first", dest="position", action="store_const", const="first", help="移到未完成项首位")
    target.add_argument("--last", dest="position", action="store_const", const="last", help="移到未完成项末尾")
    target.add_argument("--before", metavar="ITEM_ID", help="移到同列未完成事项之前")
    target.add_argument("--after", metavar="ITEM_ID", help="移到同列未完成事项之后")


def _goal_write(parser: DomainParser, *, request_id: bool = False) -> None:
    """Shared optimistic-concurrency flags for the goal CLI.

    The recovery generation is intentionally explicit.  An agent works from a
    context snapshot, and a restore replaces the database beneath that snapshot;
    accepting an old goal revision after that would still be stale.
    """
    parser.add_argument("--expected-revision", type=int, required=True)
    parser.add_argument(
        "--recovery-generation", required=True,
        help="context 中的 recoveryGeneration；空值传 none",
    )
    if request_id:
        parser.add_argument("--request-id", required=True)


def _goal_parser(top: argparse._SubParsersAction[DomainParser]) -> None:
    goal = _leaf(top, "goal", "goal.list")
    sub = goal.add_subparsers(dest="goal_cmd", required=True, parser_class=DomainParser)
    _leaf(sub, "list", "goal.list")
    show = _leaf(sub, "show", "goal.show")
    show.add_argument("goal_id")

    create = _leaf(sub, "create", "goal.create")
    create.add_argument("--title", required=True)
    create.add_argument("--notes", default="")
    create.add_argument("--horizon-text", default="")
    create.add_argument("--request-id", required=True)
    create.add_argument("--recovery-generation", required=True)

    edit = _leaf(sub, "edit", "goal.edit")
    edit.add_argument("goal_id")
    edit.add_argument("--title", required=True)
    edit.add_argument("--notes", required=True)
    edit.add_argument("--horizon-text", required=True)
    _goal_write(edit)

    state = _leaf(sub, "state", "goal.state")
    state.add_argument("goal_id")
    state.add_argument("--state", required=True, choices=("active", "paused", "ended"))
    state.add_argument("--end-reason", choices=("achieved", "abandoned"))
    _goal_write(state)

    parent = _leaf(sub, "set-parent", "goal.set-parent")
    parent.add_argument("goal_id")
    parent.add_argument("--parent-goal-id", required=True, help="主要支持目标 ID；清空传 none")
    _goal_write(parent)

    add_task = _leaf(sub, "add-task", "goal.add-task")
    add_task.add_argument("goal_id")
    add_task.add_argument("--title", required=True)
    add_task.add_argument("--notes", default="")
    add_task.add_argument("--phase-id")
    _goal_write(add_task, request_id=True)

    link_task = _leaf(sub, "link-task", "goal.link-task")
    link_task.add_argument("goal_id")
    link_task.add_argument("task_id")
    link_task.add_argument("--phase-id")
    link_task.add_argument(
        "--expected-goal-id", required=True,
        help="任务当前所属目标 ID；未关联传 none",
    )
    _goal_write(link_task)

    unlink_task = _leaf(sub, "unlink-task", "goal.unlink-task")
    unlink_task.add_argument("goal_id")
    unlink_task.add_argument("task_id")
    _goal_write(unlink_task)

    next_task = _leaf(sub, "next", "goal.next")
    next_task.add_argument("goal_id")
    next_task.add_argument("--task-id", required=True, help="任务 ID；清空传 none")
    _goal_write(next_task)

    schedule_next = _leaf(sub, "schedule-next", "goal.schedule-next")
    schedule_next.add_argument("goal_id")
    schedule_next.add_argument("--expected-task-id", required=True)
    schedule_next.add_argument(
        "--expected-scheduled-date", required=True,
        help="当前待办传 none；日期传 YYYY-MM-DD",
    )
    _goal_write(schedule_next)

    phase = _leaf(sub, "phase", "goal.phase.add")
    phase_sub = phase.add_subparsers(dest="goal_phase_cmd", required=True, parser_class=DomainParser)
    add_phase = _leaf(phase_sub, "add", "goal.phase.add")
    add_phase.add_argument("goal_id")
    add_phase.add_argument("--title", required=True)
    add_phase.add_argument("--notes", default="")
    add_phase.add_argument("--outcome", default="")
    add_phase.add_argument("--horizon-text", default="")
    _goal_write(add_phase, request_id=True)

    edit_phase = _leaf(phase_sub, "edit", "goal.phase.edit")
    edit_phase.add_argument("goal_id")
    edit_phase.add_argument("phase_id")
    edit_phase.add_argument("--title", required=True)
    edit_phase.add_argument("--notes", required=True)
    edit_phase.add_argument("--status", required=True, choices=("open", "done", "skipped"))
    edit_phase.add_argument("--outcome", default="")
    edit_phase.add_argument("--horizon-text", default="")
    _goal_write(edit_phase)

    focus_phase = _leaf(phase_sub, "focus", "goal.phase.focus")
    focus_phase.add_argument("goal_id")
    focus_phase.add_argument("--phase-id", required=True, help="阶段 ID；清空传 none")
    _goal_write(focus_phase)

    reorder = _leaf(phase_sub, "reorder", "goal.phase.reorder")
    reorder.add_argument("goal_id")
    reorder.add_argument("phase_ids", nargs="+")
    _goal_write(reorder)

    action = _leaf(sub, "action", "goal.action.add")
    action_sub = action.add_subparsers(dest="goal_action_cmd", required=True, parser_class=DomainParser)
    add_action = _leaf(action_sub, "add", "goal.action.add")
    add_action.add_argument("goal_id")
    add_action.add_argument("--title", required=True)
    add_action.add_argument("--notes", default="")
    add_action.add_argument("--phase-id")
    _goal_write(add_action, request_id=True)
    edit_action = _leaf(action_sub, "edit", "goal.action.edit")
    edit_action.add_argument("goal_id"); edit_action.add_argument("action_id")
    edit_action.add_argument("--title", required=True); edit_action.add_argument("--notes", required=True)
    edit_action.add_argument("--phase-id", required=True)
    _goal_write(edit_action)
    remove_action = _leaf(action_sub, "remove", "goal.action.remove")
    remove_action.add_argument("goal_id"); remove_action.add_argument("action_id"); _goal_write(remove_action)
    next_action = _leaf(action_sub, "next", "goal.action.next")
    next_action.add_argument("goal_id"); next_action.add_argument("--action-id", required=True, help="行动 ID；清空传 none"); _goal_write(next_action)
    materialize = _leaf(action_sub, "materialize", "goal.action.materialize")
    materialize.add_argument("goal_id"); materialize.add_argument("action_id")
    materialize.add_argument("--destination", required=True, choices=("today", "inventory")); _goal_write(materialize, request_id=True)
    link_action = _leaf(action_sub, "link", "goal.action.link")
    link_action.add_argument("goal_id"); link_action.add_argument("action_id"); link_action.add_argument("task_id")
    link_action.add_argument("--expected-task-id", required=True, help="事项 ID；未关联传 none")
    _goal_write(link_action)


def _planning_parser(top: argparse._SubParsersAction[DomainParser]) -> None:
    planner = _leaf(top, "planning", "planning.list")
    sub = planner.add_subparsers(dest="planning_cmd", required=True, parser_class=DomainParser)
    listing = _leaf(sub, "list", "planning.list")
    listing.add_argument("--goal-id")
    show = _leaf(sub, "show", "planning.show")
    show.add_argument("draft_id")
    create = _leaf(sub, "create", "planning.create")
    create.add_argument("--goal-id")
    create.add_argument("--phase-id")
    create.add_argument("--request-id", required=True)
    create.add_argument("--recovery-generation", required=True)
    for operation in ("update", "undo", "apply", "discard", "revert"):
        command = _leaf(sub, operation, f"planning.{operation}")
        command.add_argument("draft_id")
        _goal_write(command, request_id=True)
        if operation == "update":
            command.add_argument("--document-file", required=True, help="UTF-8 JSON 文档：{goals: [...]}；仅更新草案")


def build_domain_parser() -> DomainParser:
    parser = DomainParser(
        prog="python -m local_planner",
        description="Local Planner agent CLI.",
        envelope_command=None,
    )
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--human", action="store_true")
    top = parser.add_subparsers(dest="top", required=True, parser_class=DomainParser)

    _leaf(top, "meta", "meta")
    _leaf(top, "context", "context")
    _leaf(top, "capabilities", "capabilities")
    _goal_parser(top)
    _planning_parser(top)
    search = _leaf(top, "search", "search")
    search.add_argument("--query", required=True, help="按标题和备注搜索未完成事项，最多 200 字")

    calendar = _leaf(top, "calendar", "calendar")
    calendar.add_argument("--from", dest="date_from", required=True)
    calendar.add_argument("--to", dest="date_to", required=True)

    day = _leaf(top, "day", "day.open")
    day_sub = day.add_subparsers(dest="day_cmd", required=True, parser_class=DomainParser)

    day_open = _leaf(day_sub, "open", "day.open")
    day_open.add_argument("date", nargs="?", default="today")

    todo = _leaf(day_sub, "todo", "day.todo.add")
    todo_sub = todo.add_subparsers(dest="todo_cmd", required=True, parser_class=DomainParser)
    todo_add = _leaf(todo_sub, "add", "day.todo.add")
    todo_add.add_argument("date")
    todo_add.add_argument("--title", required=True)
    todo_add.add_argument("--start", dest="start_clock", default=None)
    todo_add.add_argument("--end", dest="end_clock", default=None)
    todo_complete = _leaf(todo_sub, "complete", "day.todo.complete")
    todo_complete.add_argument("date")
    todo_complete.add_argument("task_id")
    todo_uncomplete = _leaf(todo_sub, "uncomplete", "day.todo.uncomplete")
    todo_uncomplete.add_argument("date")
    todo_uncomplete.add_argument("task_id")
    todo_reorder = _leaf(todo_sub, "reorder", "day.todo.reorder")
    todo_reorder.add_argument("date")
    todo_reorder.add_argument("task_ids", nargs="*")
    todo_reorder.add_argument("--automatic", action="store_true", help="恢复按时间排序，不传 ID")
    _move(todo_sub, "todo")

    errand = _leaf(day_sub, "errand", "day.errand.add")
    errand_sub = errand.add_subparsers(dest="errand_cmd", required=True, parser_class=DomainParser)
    errand_add = _leaf(errand_sub, "add", "day.errand.add")
    errand_add.add_argument("date")
    errand_add.add_argument("--title", required=True)
    errand_add.add_argument("--start", dest="start_clock", default=None)
    errand_add.add_argument("--end", dest="end_clock", default=None)
    errand_reorder = _leaf(errand_sub, "reorder", "day.errand.reorder")
    errand_reorder.add_argument("date")
    errand_reorder.add_argument("errand_ids", nargs="*")
    errand_reorder.add_argument("--automatic", action="store_true", help="恢复按时间排序，不传 ID")
    _move(errand_sub, "errand")

    inventory = _leaf(top, "inventory", "inventory.list")
    inv_sub = inventory.add_subparsers(dest="inv_cmd", required=True, parser_class=DomainParser)
    _leaf(inv_sub, "list", "inventory.list")
    inv_add = _leaf(inv_sub, "add", "inventory.add")
    inv_add.add_argument("--title", required=True)
    inv_add.add_argument("--target-date", dest="target_date", default=None)
    inv_complete = _leaf(inv_sub, "complete", "inventory.complete")
    inv_complete.add_argument("task_id", help="直接完成待办，记入服务端今天的完成记录")

    recurrence = _leaf(top, "recurrence", "recurrence.list")
    recurrence_sub = recurrence.add_subparsers(
        dest="recurrence_cmd", required=True, parser_class=DomainParser
    )
    _leaf(recurrence_sub, "list", "recurrence.list")
    recurrence_add = _leaf(recurrence_sub, "add", "recurrence.add")
    recurrence_add.add_argument("--kind", choices=("plan", "errand"), required=True)
    recurrence_add.add_argument("--title", required=True)
    recurrence_add.add_argument(
        "--frequency", choices=("daily", "weekly"), required=True
    )
    recurrence_add.add_argument("--weekdays")
    recurrence_add.add_argument("--start-date", required=True)
    recurrence_add.add_argument("--start", dest="start_clock")
    recurrence_add.add_argument("--end", dest="end_clock")
    recurrence_update = _leaf(recurrence_sub, "update", "recurrence.update")
    recurrence_update.add_argument("series_id")
    recurrence_update.add_argument("--title", default=argparse.SUPPRESS)
    recurrence_update.add_argument(
        "--frequency", choices=("daily", "weekly"), default=argparse.SUPPRESS
    )
    recurrence_update.add_argument("--weekdays", default=argparse.SUPPRESS)
    recurrence_update.add_argument("--start-date", default=argparse.SUPPRESS)
    recurrence_update.add_argument("--start", dest="start_clock", default=argparse.SUPPRESS)
    recurrence_update.add_argument("--end", dest="end_clock", default=argparse.SUPPRESS)
    recurrence_update.add_argument("--clear-start", action="store_true")
    recurrence_update.add_argument("--clear-end", action="store_true")
    for action in ("pause", "resume", "stop", "delete"):
        action_parser = _leaf(
            recurrence_sub, action, f"recurrence.{action}"
        )
        action_parser.add_argument("series_id")

    task = _leaf(top, "task", "task.schedule")
    task_sub = task.add_subparsers(dest="task_cmd", required=True, parser_class=DomainParser)
    _edit(task_sub, "task")
    task_sched = _leaf(task_sub, "schedule", "task.schedule")
    task_sched.add_argument("task_id")
    task_sched.add_argument("--date", required=True)
    task_unsched = _leaf(task_sub, "unschedule", "task.unschedule")
    task_unsched.add_argument("task_id")
    task_rename = _leaf(task_sub, "rename", "task.rename")
    task_rename.add_argument("task_id")
    task_rename.add_argument("--title", required=True)
    task_delete = _leaf(task_sub, "delete", "task.delete")
    task_delete.add_argument("task_id")
    task_target = _leaf(task_sub, "target", "task.target")
    task_target.add_argument("task_id")
    task_target.add_argument("--date", dest="target_date", default=None)
    task_target.add_argument("--clear", action="store_true")
    todo_time = _leaf(todo_sub, "time", "day.todo.time")
    todo_time.add_argument("date")
    todo_time.add_argument("task_id")
    todo_time.add_argument("--start", dest="start_clock", default=argparse.SUPPRESS)
    todo_time.add_argument("--end", dest="end_clock", default=argparse.SUPPRESS)

    errand_top = _leaf(top, "errand", "errand.complete")
    errand_top_sub = errand_top.add_subparsers(
        dest="errand_top_cmd", required=True, parser_class=DomainParser
    )
    _edit(errand_top_sub, "errand")
    errand_complete = _leaf(errand_top_sub, "complete", "errand.complete")
    errand_complete.add_argument("errand_id")
    errand_uncomplete = _leaf(errand_top_sub, "uncomplete", "errand.uncomplete")
    errand_uncomplete.add_argument("errand_id")
    errand_rename = _leaf(errand_top_sub, "rename", "errand.rename")
    errand_rename.add_argument("errand_id")
    errand_rename.add_argument("--title", required=True)
    errand_delete = _leaf(errand_top_sub, "delete", "errand.delete")
    errand_delete.add_argument("errand_id")
    errand_time = _leaf(errand_top_sub, "time", "errand.time")
    errand_time.add_argument("errand_id")
    errand_time.add_argument("--start", dest="start_clock", default=argparse.SUPPRESS)
    errand_time.add_argument("--end", dest="end_clock", default=argparse.SUPPRESS)

    return parser
