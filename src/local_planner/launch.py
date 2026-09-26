"""The ``local-todo`` command: ensure the local web app is ready, then open it."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import ContextManager, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from local_planner.http.app import DEFAULT_PORT, HEALTH_SERVICE
from local_planner.paths import data_dir

STARTUP_TIMEOUT_SECONDS = 20.0
HEALTH_TIMEOUT_SECONDS = 0.5
POLL_SECONDS = 0.05
CHILD_EXIT_GRACE_SECONDS = 1.0
SERVER_LOG_NAME = "server.log"


class Process(Protocol):
    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


class LaunchError(RuntimeError):
    """The app could not be reached, started, or opened in a browser."""


def resolve_port(cli_port: int | None = None) -> int:
    """Use the same precedence as ``serve`` without importing its process entry."""
    if cli_port is not None:
        return cli_port
    return int(os.environ.get("LOCAL_PLANNER_PORT", str(DEFAULT_PORT)))


def app_url(port: int) -> str:
    if not 1 <= port <= 65535:
        raise LaunchError("端口必须在 1 到 65535 之间")
    return f"http://127.0.0.1:{port}/"


def service_is_ready(url: str, *, timeout: float = HEALTH_TIMEOUT_SECONDS) -> bool:
    """Return true only for this app's lock-free, data-free health response."""
    request = Request(url + "api/health", method="GET")
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 -- loopback URL
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError):
        return False
    return payload == {"ok": True, "service": HEALTH_SERVICE}


def port_is_listening(port: int, *, timeout: float = HEALTH_TIMEOUT_SECONDS) -> bool:
    """Tell an unavailable planner apart from another process owning the port."""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def server_log_path() -> Path:
    return data_dir() / SERVER_LOG_NAME


@contextmanager
def startup_lock(port: int, timeout: float) -> Iterator[None]:
    """Serialize health-miss → spawn → ready without holding planner.lock."""
    root = data_dir()
    root.mkdir(parents=True, exist_ok=True)
    fd = os.open(root / f"launch-{port}.lock", os.O_CREAT | os.O_RDWR, 0o644)
    acquired = False
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise LaunchError("等待本机计划服务启动超时") from None
                time.sleep(POLL_SECONDS)
        yield
    finally:
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def start_server(port: int) -> Process:
    """Start an independent service process; its lifetime is not tied to this CLI."""
    log_path = server_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("ab") as log_file:
        return subprocess.Popen(
            [sys.executable, "-m", "local_planner", "serve", "--port", str(port)],
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            close_fds=True,
            start_new_session=True,
        )


def open_browser(url: str) -> None:
    try:
        completed = subprocess.run(["open", url], check=False)
    except OSError as exc:
        raise LaunchError("无法打开浏览器") from exc
    if completed.returncode != 0:
        raise LaunchError("无法打开浏览器")


def _stop_owned_process(process: Process) -> None:
    """Best-effort cleanup only for the child this invocation created."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


def ensure_running(
    port: int,
    *,
    probe: Callable[[str], bool] = service_is_ready,
    listener: Callable[[int], bool] = port_is_listening,
    popen: Callable[[int], Process] = start_server,
    guard: Callable[[int, float], ContextManager[None]] = startup_lock,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    startup_timeout: float = STARTUP_TIMEOUT_SECONDS,
) -> tuple[str, bool, Process | None]:
    """Return URL plus whether this call started it, after a strict service probe."""
    url = app_url(port)
    if probe(url):
        return url, False, None
    if listener(port):
        raise LaunchError(f"端口 {port} 已被其他程序占用")

    with guard(port, startup_timeout):
        # Another local-todo may have completed while this call waited on the lock.
        if probe(url):
            return url, False, None
        if listener(port):
            raise LaunchError(f"端口 {port} 已被其他程序占用")
        try:
            process = popen(port)
        except OSError as exc:
            raise LaunchError(f"无法启动本机计划服务；日志：{server_log_path()}") from exc

        deadline = monotonic() + startup_timeout
        exit_code: int | None = None
        child_exit_deadline: float | None = None
        while True:
            now = monotonic()
            if now >= deadline or (
                child_exit_deadline is not None and now >= child_exit_deadline
            ):
                break
            if probe(url):
                return url, True, process
            code = process.poll()
            if code is not None:
                exit_code = code
                if child_exit_deadline is None:
                    child_exit_deadline = min(
                        deadline, now + CHILD_EXIT_GRACE_SECONDS
                    )
            sleep(POLL_SECONDS)

        if probe(url):
            return url, True, process
        log_path = server_log_path()
        if process.poll() is None:
            _stop_owned_process(process)
            raise LaunchError(f"本机计划服务启动超时；日志：{log_path}")
        if exit_code is None:
            exit_code = process.poll()
        raise LaunchError(
            f"本机计划服务启动失败（退出码 {exit_code}）；日志：{log_path}"
        )


def open_app(
    port: int | None = None,
    *,
    probe: Callable[[str], bool] = service_is_ready,
    listener: Callable[[int], bool] = port_is_listening,
    popen: Callable[[int], Process] = start_server,
    guard: Callable[[int, float], ContextManager[None]] = startup_lock,
    browser: Callable[[str], None] = open_browser,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    startup_timeout: float = STARTUP_TIMEOUT_SECONDS,
) -> tuple[str, bool, Process | None]:
    """Ensure the app is running, then open its numeric-loopback home page."""
    actual_port = resolve_port(port)
    url, started, process = ensure_running(
        actual_port,
        probe=probe,
        listener=listener,
        popen=popen,
        guard=guard,
        monotonic=monotonic,
        sleep=sleep,
        startup_timeout=startup_timeout,
    )
    try:
        browser(url)
    except LaunchError as exc:
        raise LaunchError(
            f"服务已就绪，但无法打开浏览器；请手动打开 {url}"
        ) from exc
    return url, started, process


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="local-todo")
    parser.add_argument("command", nargs="?", choices=("open", "serve"), default="open")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)
    if args.command == "serve":
        from local_planner.__main__ import main as planner_main

        serve_argv = ["serve"]
        if args.port is not None:
            serve_argv.extend(("--port", str(args.port)))
        return planner_main(serve_argv)
    try:
        url, started, process = open_app(args.port)
    except (LaunchError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if started and process is not None:
        print(f"已启动（PID {getattr(process, 'pid', 'unknown')}）并打开 {url}")
    else:
        print(f"已打开 {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
