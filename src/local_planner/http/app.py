"""FastAPI adapters: PLANNER_LOCK, camelCase JSON, Origin checks. Sync def routes."""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from local_planner.domain.undo import delete_with_undo, undo_delete
from local_planner.recovery import ensure_daily_backup
from local_planner.launcher_health import check_launcher
from local_planner.http.recovery_routes import mount_recovery
from local_planner.agent_receipts import build_agent_receipt
from local_planner.agent_runs import AgentRuns, RunControl
from local_planner.clock import Clock
from local_planner.domain import commands as cmds
from local_planner.domain.commands import UNSET
from local_planner.domain.recurrence import UNSET as RECURRENCE_UNSET
from local_planner.domain.errors import (
    Conflict,
    DaySealed,
    DomainError,
    NotFound,
    ValidationError,
)
from local_planner.domain.store import UnitOfWork
from local_planner.http.spa import mount_spa
from local_planner.present import (
    calendar_payload,
    command_payload,
    context_payload,
    day_plan_payload,
    inventory_item_payload,
    meta_payload,
    planning_payload,
    recurrence_payload,
)
from local_planner.launchers import (
    add_launcher,
    delete_launcher,
    load_launchers,
    run_launcher,
    update_launcher,
)
from local_planner.runtime import InternalError, LockTimeout, interprocess_lock, planner_txn

logger = logging.getLogger(__name__)

PLANNER_LOCK = threading.Lock()
DEFAULT_PORT = 8787
HEALTH_SERVICE = "local-planner"
_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


@dataclass
class AppContext:
    clock: Clock
    uow: UnitOfWork
    port: int
    dev: bool
    data_dir: Path


class TitleBody(BaseModel):
    title: str
    startClock: str | None = None
    endClock: str | None = None
    targetDate: str | None = None


class DateBody(BaseModel):
    date: str | None = None


class ClockBody(BaseModel):
    startClock: str | None = None
    endClock: str | None = None


class LauncherBody(BaseModel):
    name: str
    command: str


class PromptBody(BaseModel):
    prompt: str
    surface: Literal["today", "todo", "day"] = "today"
    date: str | None = None


class AgentRunBody(PromptBody):
    launcherId: str
    requestId: str = Field(min_length=1, max_length=100)
    prompt: str = Field(min_length=1, max_length=10000)


class RecurrenceCreateBody(BaseModel):
    kind: str
    title: str
    frequency: str
    weekdays: list[str] | None = None
    startDate: str
    defaultStartClock: str | None = None
    defaultEndClock: str | None = None


class RecurrenceUpdateBody(BaseModel):
    title: str | None = None
    frequency: str | None = None
    weekdays: list[str] | None = None
    startDate: str | None = None
    defaultStartClock: str | None = None
    defaultEndClock: str | None = None


class TaskOrderBody(BaseModel):
    taskIds: list[str]


class ErrandOrderBody(BaseModel):
    errandIds: list[str]


def health() -> dict[str, bool | str]:
    """Liveness only: no lock, no settle, no data."""
    return {"ok": True, "service": HEALTH_SERVICE}


def _locked(ctx: AppContext, fn: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    with PLANNER_LOCK:
        with interprocess_lock(ctx.data_dir):
            try:
                conn = getattr(ctx.uow, "conn", None)
                if conn is not None:
                    try:
                        ensure_daily_backup(conn, ctx.data_dir, ctx.clock.today())
                    except (OSError, sqlite3.Error):
                        logger.exception("automatic backup failed")
                with planner_txn(ctx.clock, ctx.uow) as today:
                    return fn(today)
            except sqlite3.OperationalError as exc:
                raise InternalError("内部错误") from exc


def debug_payload(uow: UnitOfWork, today: str) -> dict[str, Any]:
    conn = getattr(uow, "conn", None)
    if conn is None:
        raise NotFound("找不到调试信息")
    file_row = conn.execute("PRAGMA database_list").fetchone()
    db_file = file_row["file"] if file_row is not None else ""
    schema = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
    integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    return {
        "today": today,
        "timezone": "Asia/Shanghai",
        "lastSettledDate": uow.meta.get("last_settled_date"),
        "dbPath": db_file,
        "schemaVersion": int(schema or 0),
        "integrityCheck": integrity,
        "counts": {
            "tasks": conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
            "openDays": conn.execute(
                "SELECT COUNT(*) FROM days WHERE status = 'open'"
            ).fetchone()[0],
            "sealedDays": conn.execute(
                "SELECT COUNT(*) FROM days WHERE status = 'sealed'"
            ).fetchone()[0],
            "errands": conn.execute("SELECT COUNT(*) FROM errands").fetchone()[0],
        },
    }


def allowed_origins(port: int, dev: bool) -> set[str]:
    allowed = {f"http://127.0.0.1:{port}"}
    if dev:
        allowed.add("http://127.0.0.1:5173")
        allowed.add("http://localhost:5173")
    return allowed


def _error_status(exc: DomainError) -> int:
    if isinstance(exc, ValidationError):
        return 400
    if isinstance(exc, NotFound):
        return 404
    if isinstance(exc, (DaySealed, Conflict)):
        return 409
    return 500


def _error_body(exc: DomainError) -> dict[str, str]:
    return {"error": exc.code, "message": exc.message}


def _data_dir_from_uow(uow: UnitOfWork) -> Path:
    """Derive lock dir from this uow's sqlite file. Never the production data dir."""
    conn = getattr(uow, "conn", None)
    if conn is None:
        raise ValueError("create_app 需要 data_dir")
    row = conn.execute("PRAGMA database_list").fetchone()
    db_file = ""
    if row is not None:
        try:
            db_file = row["file"]
        except (KeyError, IndexError, TypeError):
            db_file = row[2] if len(row) > 2 else ""
    if not db_file:
        raise ValueError("create_app 需要 data_dir")
    return Path(db_file).parent


def create_app(
    *,
    clock: Clock,
    uow: UnitOfWork,
    port: int = DEFAULT_PORT,
    dev: bool | None = None,
    dist_dir: Path | None = None,
    data_dir: Path | None = None,
) -> FastAPI:
    if dev is None:
        dev = os.environ.get("LOCAL_PLANNER_DEV") == "1"
    if data_dir is None:
        data_dir = _data_dir_from_uow(uow)
    ctx = AppContext(clock=clock, uow=uow, port=port, dev=dev, data_dir=data_dir)
    runs = AgentRuns(data_dir)
    deletions: dict[str, tuple] = {}

    def remember_deletion(kind: str, entity_id: str) -> dict:
        change = delete_with_undo(clock, uow, kind, entity_id)
        token = str(uuid.uuid4())
        now = time.monotonic()
        for key, record in list(deletions.items()):
            if now - record[0] > 300:
                del deletions[key]
        while len(deletions) >= 100:
            del deletions[next(iter(deletions))]
        deletions[token] = (now, change, uow.meta.get("recovery_generation"))
        return {"token": token, "title": change.before.title}

    @asynccontextmanager
    async def lifespan(_app):
        yield
        runs.close()

    app = FastAPI(
        lifespan=lifespan,
        title="Local Planner",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.ctx = ctx
    app.state.agent_runs = runs

    @app.middleware("http")
    async def origin_and_log(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.method in _MUTATING:
            origin = request.headers.get("origin")
            if origin:
                if origin not in allowed_origins(ctx.port, ctx.dev):
                    logger.info(
                        "http method=%s path=%s status=403 ms=0",
                        request.method,
                        request.url.path,
                    )
                    return JSONResponse(
                        {"error": "Forbidden", "message": "不允许的 Origin"},
                        status_code=403,
                    )
            content_type = request.headers.get("content-type")
            if content_type is not None:
                mime = content_type.split(";", 1)[0].strip().lower()
                if mime != "application/json":
                    return JSONResponse(
                        {
                            "error": "ValidationError",
                            "message": "Content-Type 必须是 application/json",
                        },
                        status_code=400,
                    )
        started = time.perf_counter()
        response = await call_next(request)
        ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "http method=%s path=%s status=%s ms=%s",
            request.method,
            request.url.path,
            response.status_code,
            ms,
        )
        return response

    @app.exception_handler(DomainError)
    def domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        if isinstance(exc, DaySealed):
            logger.info(
                "reject code=DaySealed date=%s path=%s",
                exc.date,
                _request.url.path,
            )
        return JSONResponse(_error_body(exc), status_code=_error_status(exc))

    @app.exception_handler(LockTimeout)
    def lock_timeout(_request: Request, exc: LockTimeout) -> JSONResponse:
        return JSONResponse(
            {"error": exc.code, "message": exc.message},
            status_code=503,
        )

    @app.exception_handler(InternalError)
    def internal_error(_request: Request, exc: InternalError) -> JSONResponse:
        return JSONResponse(
            {"error": exc.code, "message": exc.message},
            status_code=500,
        )

    @app.exception_handler(RequestValidationError)
    def invalid_request(_request: Request, _exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {"error": "ValidationError", "message": "请求无效"},
            status_code=400,
        )

    @app.exception_handler(StarletteHTTPException)
    def http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return JSONResponse(
                {"error": "NotFound", "message": "找不到该资源"},
                status_code=404,
            )
        return JSONResponse(
            {"error": "Error", "message": str(exc.detail)},
            status_code=exc.status_code,
        )

    @app.get("/api/health")
    def health_route() -> dict[str, bool | str]:
        return health()

    @app.get("/api/meta")
    def get_meta() -> dict[str, Any]:
        return _locked(ctx, lambda today: meta_payload(ctx.uow, today))

    @app.get("/api/debug")
    def get_debug() -> dict[str, Any]:
        return _locked(ctx, lambda today: debug_payload(ctx.uow, today))

    @app.get("/api/days/{day_date}")
    def open_day(day_date: str) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: day_plan_payload(
                cmds.open_day(ctx.clock, ctx.uow, day_date), today
            ),
        )

    @app.get("/api/inventory")
    def list_inventory() -> dict[str, Any]:
        return _locked(
            ctx,
            lambda _today: {
                "items": [
                    inventory_item_payload(item)
                    for item in cmds.list_inventory(ctx.uow)
                ]
            },
        )

    @app.get("/api/calendar")
    def get_calendar(
        from_: str = Query(..., alias="from"),
        to: str = Query(...),
    ) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: calendar_payload(ctx.uow, from_, to, today),
        )

    @app.post("/api/days/{day_date}/todos")
    def add_todo(day_date: str, body: TitleBody) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: day_plan_payload(
                cmds.add_todo_on_day(
                    ctx.clock,
                    ctx.uow,
                    day_date,
                    body.title,
                    body.startClock,
                    body.endClock,
                ),
                today,
            ),
        )

    @app.post("/api/inventory/tasks")
    def add_inventory(body: TitleBody) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: command_payload(
                cmds.add_to_inventory(
                    ctx.clock, ctx.uow, body.title, body.targetDate
                ), today
            ),
        )

    @app.post("/api/tasks/{task_id}/schedule")
    def schedule(task_id: str, body: DateBody) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: day_plan_payload(
                cmds.schedule_to_date(ctx.clock, ctx.uow, task_id, body.date or ""),
                today,
            ),
        )

    @app.post("/api/tasks/{task_id}/unschedule")
    def unschedule(task_id: str) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: command_payload(
                cmds.unschedule(ctx.clock, ctx.uow, task_id), today
            ),
        )

    @app.post("/api/days/{day_date}/todos/{task_id}/complete")
    def complete_todo(day_date: str, task_id: str) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: day_plan_payload(
                cmds.complete_task_on_day(ctx.clock, ctx.uow, task_id, day_date),
                today,
            ),
        )

    @app.post("/api/days/{day_date}/todos/{task_id}/uncomplete")
    def uncomplete_todo(day_date: str, task_id: str) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: day_plan_payload(
                cmds.uncomplete_task_on_day(ctx.clock, ctx.uow, task_id, day_date),
                today,
            ),
        )

    @app.post("/api/days/{day_date}/errands")
    def add_errand(day_date: str, body: TitleBody) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: day_plan_payload(
                cmds.add_errand(
                    ctx.clock,
                    ctx.uow,
                    day_date,
                    body.title,
                    body.startClock,
                    body.endClock,
                ), today
            ),
        )

    @app.post("/api/errands/{errand_id}/complete")
    def complete_errand(errand_id: str) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: day_plan_payload(
                cmds.complete_errand(ctx.clock, ctx.uow, errand_id), today
            ),
        )

    @app.post("/api/errands/{errand_id}/uncomplete")
    def uncomplete_errand(errand_id: str) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: day_plan_payload(
                cmds.uncomplete_errand(ctx.clock, ctx.uow, errand_id), today
            ),
        )

    @app.delete("/api/errands/{errand_id}")
    def delete_errand(errand_id: str) -> dict[str, Any]:
        def inner(today):
            undo = remember_deletion("errand", errand_id)
            change = deletions[undo["token"]][1]
            return day_plan_payload(cmds.open_day(clock, uow, change.before.day_date), today) | {"undo": undo}
        return _locked(ctx, inner)

    @app.patch("/api/errands/{errand_id}")
    def rename_errand(errand_id: str, body: TitleBody) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: day_plan_payload(
                cmds.rename_errand(ctx.clock, ctx.uow, errand_id, body.title),
                today,
            ),
        )

    @app.patch("/api/tasks/{task_id}")
    def rename_task(task_id: str, body: TitleBody) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: command_payload(
                cmds.rename_task(ctx.clock, ctx.uow, task_id, body.title), today
            ),
        )

    @app.post("/api/inventory/tasks/{task_id}/complete")
    def complete_inventory_task(task_id: str) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: day_plan_payload(
                cmds.complete_inventory_task(ctx.clock, ctx.uow, task_id), today
            ),
        )

    @app.delete("/api/tasks/{task_id}")
    def delete_task(task_id: str) -> dict[str, Any]:
        def inner(today: str) -> dict[str, Any]:
            undo = remember_deletion("task", task_id)
            return command_payload(None, today) | {"undo": undo}

        return _locked(ctx, inner)

    @app.put("/api/days/{day_date}/todos/order")
    def reorder_todos(day_date: str, body: TaskOrderBody) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: day_plan_payload(
                cmds.reorder_todos(ctx.clock, ctx.uow, day_date, body.taskIds),
                today,
            ),
        )

    @app.patch("/api/tasks/{task_id}/target")
    def set_target(task_id: str, body: DateBody) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: command_payload(
                cmds.set_target_date(ctx.clock, ctx.uow, task_id, body.date),
                today,
            ),
        )

    @app.patch("/api/days/{day_date}/todos/{task_id}/clocks")
    def set_todo_clocks(
        day_date: str, task_id: str, body: ClockBody
    ) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: day_plan_payload(
                cmds.set_plan_clocks(
                    ctx.clock,
                    ctx.uow,
                    day_date,
                    task_id,
                    body.startClock if "startClock" in body.model_fields_set else UNSET,
                    body.endClock if "endClock" in body.model_fields_set else UNSET,
                ),
                today,
            ),
        )

    @app.patch("/api/errands/{errand_id}/clocks")
    def set_errand_clocks(errand_id: str, body: ClockBody) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: day_plan_payload(
                cmds.set_errand_clocks(
                    ctx.clock,
                    ctx.uow,
                    errand_id,
                    body.startClock if "startClock" in body.model_fields_set else UNSET,
                    body.endClock if "endClock" in body.model_fields_set else UNSET,
                ),
                today,
            ),
        )

    @app.put("/api/days/{day_date}/errands/order")
    def reorder_errands(day_date: str, body: ErrandOrderBody) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: day_plan_payload(
                cmds.reorder_errands(ctx.clock, ctx.uow, day_date, body.errandIds),
                today,
            ),
        )

    @app.get("/api/recurrences")
    def list_recurrences() -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: {
                "items": [
                    recurrence_payload(item, today)
                    for item in cmds.list_recurrences(ctx.uow)
                ]
            },
        )

    @app.post("/api/recurrences")
    def create_recurrence(body: RecurrenceCreateBody) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: recurrence_payload(
                cmds.create_recurrence(
                    ctx.clock,
                    ctx.uow,
                    kind=body.kind,
                    title=body.title,
                    frequency=body.frequency,
                    weekdays=body.weekdays,
                    start_date=body.startDate,
                    default_start_clock=body.defaultStartClock,
                    default_end_clock=body.defaultEndClock,
                ),
                today,
            ),
        )

    @app.patch("/api/recurrences/{series_id}")
    def patch_recurrence(
        series_id: str, body: RecurrenceUpdateBody
    ) -> dict[str, Any]:
        fields = body.model_fields_set
        return _locked(
            ctx,
            lambda today: recurrence_payload(
                cmds.update_recurrence(
                    ctx.clock,
                    ctx.uow,
                    series_id,
                    title=body.title if "title" in fields else RECURRENCE_UNSET,
                    frequency=(
                        body.frequency
                        if "frequency" in fields
                        else RECURRENCE_UNSET
                    ),
                    weekdays=(
                        body.weekdays if "weekdays" in fields else RECURRENCE_UNSET
                    ),
                    start_date=(
                        body.startDate if "startDate" in fields else RECURRENCE_UNSET
                    ),
                    default_start_clock=(
                        body.defaultStartClock
                        if "defaultStartClock" in fields
                        else RECURRENCE_UNSET
                    ),
                    default_end_clock=(
                        body.defaultEndClock
                        if "defaultEndClock" in fields
                        else RECURRENCE_UNSET
                    ),
                ),
                today,
            ),
        )

    @app.post("/api/recurrences/{series_id}/pause")
    def pause_recurrence(series_id: str) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: recurrence_payload(
                cmds.pause_recurrence(ctx.clock, ctx.uow, series_id), today
            ),
        )

    @app.post("/api/recurrences/{series_id}/resume")
    def resume_recurrence(series_id: str) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: recurrence_payload(
                cmds.resume_recurrence(ctx.clock, ctx.uow, series_id), today
            ),
        )

    @app.post("/api/recurrences/{series_id}/stop")
    def stop_recurrence(series_id: str) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: recurrence_payload(
                cmds.stop_recurrence(ctx.clock, ctx.uow, series_id), today
            ),
        )

    @app.delete("/api/recurrences/{series_id}")
    def delete_recurrence(series_id: str) -> dict[str, Any]:
        def apply_delete(_today: str) -> dict[str, Any]:
            undo = remember_deletion("recurrence", series_id)
            return {"ok": True, "undo": undo}

        return _locked(
            ctx,
            apply_delete,
        )

    @app.get("/api/planning/today")
    def get_planning_today() -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: planning_payload(
                cmds.open_planning_today(ctx.clock, ctx.uow), today
            ),
        )

    @app.post("/api/planning/today/complete")
    def complete_planning_today() -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: planning_payload(
                cmds.complete_planning_today(ctx.clock, ctx.uow), today
            ),
        )

    @app.post("/api/undo/{token}")
    def undo_deletion(token: str):
        def inner(today):
            record = deletions.get(token)
            if record is None or time.monotonic() - record[0] > 300:
                raise Conflict("撤销已过期，必要时可从设置中恢复备份")
            if record[2] != uow.meta.get("recovery_generation"):
                raise Conflict("数据已经恢复过，无法撤销此前的操作")
            undo_delete(clock, uow, record[1])
            return {"ok": True, "today": today}
        result = _locked(ctx, inner)
        deletions.pop(token, None)
        return result

    @app.post("/api/launchers/{launcher_id}/check")
    def check_agent(launcher_id: str):
        item = next((item for item in load_launchers(ctx.data_dir) if item.id == launcher_id), None)
        if item is None:
            raise NotFound("找不到该助手")
        return check_launcher(item)

    @app.get("/api/launchers")
    def get_launchers() -> dict[str, Any]:
        items = load_launchers(ctx.data_dir)
        return {
            "items": [
                {"id": item.id, "name": item.name, "command": item.command}
                for item in items
            ]
        }

    @app.post("/api/launchers")
    def create_launcher(body: LauncherBody) -> dict[str, Any]:
        try:
            item = add_launcher(body.name, body.command, ctx.data_dir)
        except ValueError as exc:
            raise ValidationError(str(exc)) from None
        return {"id": item.id, "name": item.name, "command": item.command}

    @app.patch("/api/launchers/{launcher_id}")
    def patch_launcher(launcher_id: str, body: LauncherBody) -> dict[str, Any]:
        try:
            item = update_launcher(
                launcher_id, body.name, body.command, ctx.data_dir
            )
        except KeyError:
            raise NotFound("找不到该启动器") from None
        except ValueError as exc:
            raise ValidationError(str(exc)) from None
        return {"id": item.id, "name": item.name, "command": item.command}

    @app.delete("/api/launchers/{launcher_id}")
    def remove_launcher(launcher_id: str) -> dict[str, Any]:
        try:
            delete_launcher(launcher_id, ctx.data_dir)
        except KeyError:
            raise NotFound("找不到该启动器") from None
        return {"ok": True}

    def execute_agent(launcher_id: str, body: PromptBody, control: RunControl | None = None) -> dict[str, Any]:
        items = load_launchers(ctx.data_dir)
        found = next((item for item in items if item.id == launcher_id), None)
        if found is None:
            raise NotFound("找不到该启动器")
        before = _locked(
            ctx,
            lambda today: context_payload(ctx.clock, ctx.uow, today),
        )
        result = run_launcher(
            found,
            body.prompt,
            timeout=600,
            clock=ctx.clock,
            data_root=ctx.data_dir,
            surface=body.surface,
            date=body.date,
            **({"control": control} if control else {}),
        )
        after = _locked(
            ctx,
            lambda today: context_payload(ctx.clock, ctx.uow, today),
        )
        receipt = build_agent_receipt(before, after)
        status = (
            "succeeded"
            if result.ok
            else ("failed_with_changes" if receipt["changed"] else "failed")
        )
        if control and control.cancelled:
            status = "stopped_with_changes" if receipt["changed"] else "stopped"
        return {
            "ok": result.ok and not (control and control.cancelled),
            "status": status,
            "message": "已停止本次执行，已经保存的改动会保留。" if control and control.cancelled else (None if result.ok else "执行未完成，可能已有部分改动，请核对计划。"),
            "receipt": receipt,
            "argv": result.argv,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    @app.post("/api/launchers/{launcher_id}/run")
    def run_agent(launcher_id: str, body: PromptBody) -> dict[str, Any]:
        # Legacy synchronous callers also participate in the one-run lease.
        if not any(item.id == launcher_id for item in load_launchers(ctx.data_dir)):
            raise NotFound("找不到该启动器")
        run = runs.start(str(uuid.uuid4()), launcher_id, body.prompt,
                         lambda control: execute_agent(launcher_id, body, control), surface=body.surface, date=body.date)
        while (latest := runs.get(run["id"]))["result"] is None:
            time.sleep(0.02)
        return latest["result"]

    @app.post("/api/agent-runs", status_code=202)
    def start_agent(body: AgentRunBody) -> dict[str, Any]:
        if not body.prompt.strip():
            raise ValidationError("请先写下要助手做的事")
        if not any(item.id == body.launcherId for item in load_launchers(ctx.data_dir)):
            raise NotFound("找不到该启动器")
        return runs.start(body.requestId, body.launcherId, body.prompt,
                          lambda control: execute_agent(body.launcherId, body, control), surface=body.surface, date=body.date)

    @app.get("/api/agent-runs")
    def latest_agent() -> dict[str, Any]:
        return {"run": runs.get()}

    @app.get("/api/agent-runs/{run_id}")
    def get_agent(run_id: str) -> dict[str, Any]:
        return runs.get(run_id)

    @app.post("/api/agent-runs/{run_id}/{action}")
    def control_agent(run_id: str, action: Literal["pause", "resume", "stop"]) -> dict[str, Any]:
        return runs.control(run_id, action)

    mount_recovery(app, ctx, PLANNER_LOCK)

    if dist_dir is not None:
        mount_spa(app, dist_dir)

    return app
