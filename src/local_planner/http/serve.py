"""Process entry: loopback uvicorn, startup settle, 30s timer. Owns PLANNER_LOCK."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

import uvicorn

from local_planner.clock import Clock, FrozenClock, SystemClock
from local_planner.domain.settlement import ensure_settled
from local_planner.domain.store import UnitOfWork
from local_planner.http.app import DEFAULT_PORT, PLANNER_LOCK, create_app
from local_planner.persistence import SqliteUnitOfWork

logger = logging.getLogger(__name__)

DB_NAME = "planner.sqlite"
SETTLE_INTERVAL_SECONDS = 30


def data_dir() -> Path:
    override = os.environ.get("LOCAL_PLANNER_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if os.environ.get("LOCAL_PLANNER_DEV") == "1":
        return Path(__file__).resolve().parents[3] / ".data"
    return Path.home() / "Library" / "Application Support" / "local-planner"


def db_path() -> Path:
    return data_dir() / DB_NAME


def resolve_port(cli_port: int | None = None) -> int:
    if cli_port is not None:
        return cli_port
    return int(os.environ.get("LOCAL_PLANNER_PORT", str(DEFAULT_PORT)))


def resolve_clock() -> Clock:
    pinned = os.environ.get("LOCAL_PLANNER_CLOCK")
    allowed = os.environ.get("LOCAL_PLANNER_ALLOW_CLOCK_OVERRIDE") == "1"
    if pinned and allowed:
        return FrozenClock(pinned)
    return SystemClock()


def uvicorn_run_kwargs(port: int) -> dict[str, object]:
    return {
        "host": "127.0.0.1",
        "port": port,
        "workers": 1,
        "reload": False,
    }


class SettlementTimer:
    """Background thread: same lock → transaction → ensure_settled path as HTTP."""

    def __init__(
        self,
        clock: Clock,
        uow: UnitOfWork,
        interval: float = SETTLE_INTERVAL_SECONDS,
    ) -> None:
        self._clock = clock
        self._uow = uow
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._loop, name="local-planner-settle", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                with PLANNER_LOCK:
                    with self._uow.transaction():
                        ensure_settled(self._clock, self._uow)
            except Exception:
                logger.exception("periodic ensure_settled failed")


def serve(port: int | None = None) -> None:
    logging.basicConfig(
        level=getattr(
            logging, os.environ.get("LOCAL_PLANNER_LOG", "INFO").upper(), logging.INFO
        )
    )
    port = resolve_port(port)
    clock = resolve_clock()
    path = db_path()
    uow = SqliteUnitOfWork.open(path)
    app = create_app(
        clock=clock,
        uow=uow,
        port=port,
        dev=os.environ.get("LOCAL_PLANNER_DEV") == "1",
    )
    with PLANNER_LOCK:
        with uow.transaction():
            ensure_settled(clock, uow)
            today = clock.today()
            last = uow.meta.get("last_settled_date")
    logger.info(
        "startup data_dir=%s db=%s today=%s last_settled=%s",
        data_dir(),
        path,
        today,
        last,
    )
    print(f"http://127.0.0.1:{port}", flush=True)
    timer = SettlementTimer(clock, uow)
    timer.start()
    try:
        uvicorn.run(app, **uvicorn_run_kwargs(port))
    finally:
        timer.stop()
        uow.close()
