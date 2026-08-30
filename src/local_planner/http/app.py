"""FastAPI adapters: PLANNER_LOCK, camelCase JSON, Origin checks. Sync def routes."""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from local_planner.clock import Clock
from local_planner.domain import commands as cmds
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
    day_plan_payload,
    inventory_item_payload,
    meta_payload,
)
from local_planner.runtime import InternalError, LockTimeout, interprocess_lock, planner_txn

logger = logging.getLogger(__name__)

PLANNER_LOCK = threading.Lock()
DEFAULT_PORT = 8787
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


class DateBody(BaseModel):
    date: str


class TaskOrderBody(BaseModel):
    taskIds: list[str]


class ErrandOrderBody(BaseModel):
    errandIds: list[str]


def health() -> dict[str, bool]:
    """Liveness only: no lock, no settle, no data."""
    return {"ok": True}


def _locked(ctx: AppContext, fn: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    with PLANNER_LOCK:
        with interprocess_lock(ctx.data_dir):
            try:
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
    app = FastAPI(
        title="Local Planner",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.ctx = ctx

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
    def health_route() -> dict[str, bool]:
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
                cmds.add_todo_on_day(ctx.clock, ctx.uow, day_date, body.title),
                today,
            ),
        )

    @app.post("/api/inventory/tasks")
    def add_inventory(body: TitleBody) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: command_payload(
                cmds.add_to_inventory(ctx.clock, ctx.uow, body.title), today
            ),
        )

    @app.post("/api/tasks/{task_id}/schedule")
    def schedule(task_id: str, body: DateBody) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: day_plan_payload(
                cmds.schedule_to_date(ctx.clock, ctx.uow, task_id, body.date),
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
                cmds.add_errand(ctx.clock, ctx.uow, day_date, body.title), today
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
        return _locked(
            ctx,
            lambda today: day_plan_payload(
                cmds.delete_errand(ctx.clock, ctx.uow, errand_id), today
            ),
        )

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

    @app.delete("/api/tasks/{task_id}")
    def delete_task(task_id: str) -> dict[str, Any]:
        def inner(today: str) -> dict[str, Any]:
            cmds.delete_task(ctx.clock, ctx.uow, task_id)
            return command_payload(None, today)

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

    @app.put("/api/days/{day_date}/errands/order")
    def reorder_errands(day_date: str, body: ErrandOrderBody) -> dict[str, Any]:
        return _locked(
            ctx,
            lambda today: day_plan_payload(
                cmds.reorder_errands(ctx.clock, ctx.uow, day_date, body.errandIds),
                today,
            ),
        )

    if dist_dir is not None:
        mount_spa(app, dist_dir)

    return app
