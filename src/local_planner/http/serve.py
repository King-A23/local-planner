"""Process entry: loopback uvicorn, startup settle, 30s timer. Owns PLANNER_LOCK."""

from __future__ import annotations

import logging
import os
import sys
import threading
from collections.abc import Callable
from pathlib import Path

import uvicorn

from local_planner.clock import Clock
from local_planner.domain.store import UnitOfWork
from local_planner.http.app import DEFAULT_PORT, PLANNER_LOCK, create_app
from local_planner.http.spa import resolve_web_dist
from local_planner.paths import data_dir, db_path, resolve_clock
from local_planner.runtime import (
    LockTimeout,
    configure_logging,
    interprocess_lock,
    open_persistent_uow,
    planner_txn,
)

logger = logging.getLogger(__name__)

SETTLE_INTERVAL_SECONDS = 30


def resolve_port(cli_port: int | None = None) -> int:
    if cli_port is not None:
        return cli_port
    return int(os.environ.get("LOCAL_PLANNER_PORT", str(DEFAULT_PORT)))


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
        data_dir: Path,
        interval: float = SETTLE_INTERVAL_SECONDS,
    ) -> None:
        self._clock = clock
        self._uow = uow
        self._data_dir = data_dir
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
                    try:
                        with interprocess_lock(self._data_dir, timeout=0):
                            with planner_txn(self._clock, self._uow):
                                pass
                    except LockTimeout:
                        logger.info("code=LockTimeout wait_s=0 skip")
            except Exception:
                logger.exception("periodic ensure_settled failed")


def serve(port: int | None = None, *, runner: Callable | None = None) -> None:
    configure_logging()
    port = resolve_port(port)
    clock = resolve_clock()
    ddir, path = data_dir(), db_path()
    try:
        uow = open_persistent_uow(ddir, path, clock)
    except LockTimeout:
        print("计划正忙，请重试", file=sys.stderr)
        raise SystemExit(3)
    dev = os.environ.get("LOCAL_PLANNER_DEV") == "1"
    dist = resolve_web_dist()
    if dist is None and not dev:
        print("Missing web/dist/index.html; run npm run build", file=sys.stderr)
        uow.close()
        raise SystemExit(1)
    last = uow.meta.get("last_settled_date")
    logger.info(
        "startup data_dir=%s db=%s today=%s last_settled=%s",
        ddir,
        path,
        clock.today(),
        last,
    )
    app = create_app(
        clock=clock,
        uow=uow,
        port=port,
        dev=dev,
        dist_dir=dist,
        data_dir=ddir,
    )
    print(f"http://127.0.0.1:{port}", flush=True)
    timer = SettlementTimer(clock, uow, ddir)
    timer.start()
    try:
        (runner or uvicorn.run)(app, **uvicorn_run_kwargs(port))
    finally:
        timer.stop()
        uow.close()
