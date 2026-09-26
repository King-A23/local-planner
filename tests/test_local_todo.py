"""The local-todo launcher never opens a real browser during tests."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import nullcontext
import socket
import subprocess
from pathlib import Path

import pytest

from local_planner import launch


def _no_lock(_port: int, _timeout: float):
    return nullcontext()


class FakeProcess:
    def __init__(self, code: int | None = None) -> None:
        self.code = code
        self.terminated = False
        self.killed = False
        self.pid = 4321

    def poll(self) -> int | None:
        return self.code

    def terminate(self) -> None:
        self.terminated = True
        self.code = 0

    def kill(self) -> None:
        self.killed = True
        self.code = -9

    def wait(self, timeout: float | None = None) -> int:
        if self.code is None:
            raise AssertionError("fake process must be stopped first")
        return self.code


def _times(*values: float) -> Iterator[float]:
    return iter(values)


def test_existing_service_opens_without_spawning() -> None:
    opened: list[str] = []

    url, started, process = launch.open_app(
        9020,
        probe=lambda value: value == "http://127.0.0.1:9020/",
        listener=lambda _port: False,
        popen=lambda _port: pytest.fail("must not spawn"),
        guard=_no_lock,
        browser=opened.append,
    )

    assert (url, started, process) == ("http://127.0.0.1:9020/", False, None)
    assert opened == [url]


def test_starts_then_waits_for_dedicated_health_before_opening() -> None:
    process = FakeProcess()
    opened: list[str] = []
    probes = iter((False, False, True))
    spawned: list[int] = []

    url, started, returned = launch.open_app(
        9021,
        probe=lambda _url: next(probes),
        listener=lambda _port: False,
        popen=lambda port: (spawned.append(port) or process),
        guard=_no_lock,
        browser=opened.append,
        monotonic=lambda: 0,
        sleep=lambda _seconds: None,
    )

    assert (url, started, returned) == ("http://127.0.0.1:9021/", True, process)
    assert spawned == [9021]
    assert opened == [url]


def test_port_race_waits_for_other_launcher_service_after_own_child_exits() -> None:
    process = FakeProcess(code=48)
    probes = iter((False, False, False, True))
    opened: list[str] = []

    url, started, returned = launch.open_app(
        9022,
        probe=lambda _url: next(probes),
        listener=lambda _port: False,
        popen=lambda _port: process,
        guard=_no_lock,
        browser=opened.append,
        monotonic=lambda: 0,
        sleep=lambda _seconds: None,
    )

    assert started is True
    assert returned is process
    assert opened == [url]


def test_timeout_stops_only_the_child_started_by_this_invocation() -> None:
    process = FakeProcess()
    times = _times(0, 0, 2)

    with pytest.raises(launch.LaunchError, match="超时"):
        launch.ensure_running(
            9023,
            probe=lambda _url: False,
            listener=lambda _port: False,
            popen=lambda _port: process,
            guard=_no_lock,
            monotonic=lambda: next(times),
            sleep=lambda _seconds: None,
            startup_timeout=1,
        )

    assert process.terminated is True
    assert process.killed is False


def test_main_defaults_to_open_and_honors_port(monkeypatch, capsys) -> None:
    calls: list[int | None] = []

    def fake_open(port: int | None = None):
        calls.append(port)
        return "http://127.0.0.1:9123/", False, None

    monkeypatch.setattr(launch, "open_app", fake_open)
    assert launch.main([]) == 0
    assert launch.main(["open", "--port", "9124"]) == 0
    assert calls == [None, 9124]
    assert "127.0.0.1:9123" in capsys.readouterr().out


def test_invalid_port_never_spawns_or_opens() -> None:
    with pytest.raises(launch.LaunchError, match="端口"):
        launch.open_app(
            0,
            probe=lambda _url: pytest.fail("must not probe"),
            listener=lambda _port: pytest.fail("must not inspect port"),
            popen=lambda _port: pytest.fail("must not spawn"),
            guard=_no_lock,
            browser=lambda _url: pytest.fail("must not open"),
        )


def test_foreign_listener_is_rejected_without_spawning_or_opening() -> None:
    with pytest.raises(launch.LaunchError, match="其他程序占用"):
        launch.open_app(
            9024,
            probe=lambda _url: False,
            listener=lambda port: port == 9024,
            popen=lambda _port: pytest.fail("must not spawn"),
            guard=_no_lock,
            browser=lambda _url: pytest.fail("must not open"),
        )


def test_waiter_reprobes_inside_startup_lock_and_does_not_spawn() -> None:
    probes = iter((False, True))
    entered: list[tuple[int, float]] = []

    def guard(port: int, timeout: float):
        entered.append((port, timeout))
        return nullcontext()

    url, started, process = launch.ensure_running(
        9025,
        probe=lambda _url: next(probes),
        listener=lambda _port: False,
        popen=lambda _port: pytest.fail("must not spawn"),
        guard=guard,
        startup_timeout=3,
    )

    assert (url, started, process) == ("http://127.0.0.1:9025/", False, None)
    assert entered == [(9025, 3)]


def test_browser_failure_reports_ready_service_url() -> None:
    def fail_browser(_url: str) -> None:
        raise launch.LaunchError("open failed")

    with pytest.raises(launch.LaunchError, match="服务已就绪.*手动打开"):
        launch.open_app(
            9026,
            probe=lambda _url: True,
            listener=lambda _port: False,
            popen=lambda _port: pytest.fail("must not spawn"),
            guard=_no_lock,
            browser=fail_browser,
        )


def test_local_todo_serve_delegates_without_opening(monkeypatch) -> None:
    calls: list[list[str]] = []

    monkeypatch.setattr(
        "local_planner.__main__.main",
        lambda argv: calls.append(argv) or 0,
    )
    monkeypatch.setattr(
        launch,
        "open_app",
        lambda *_args, **_kwargs: pytest.fail("must not open"),
    )

    assert launch.main(["serve", "--port", "9030"]) == 0
    assert calls == [["serve", "--port", "9030"]]


def test_start_server_redirects_to_stable_log(monkeypatch, tmp_path: Path) -> None:
    seen: dict[str, object] = {}
    process = FakeProcess()

    def fake_popen(argv, **kwargs):
        seen["argv"] = argv
        seen.update(kwargs)
        return process

    monkeypatch.setattr(launch, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(launch.subprocess, "Popen", fake_popen)

    assert launch.start_server(9031) is process
    assert seen["argv"][-3:] == ["serve", "--port", "9031"]
    assert seen["stderr"] is subprocess.STDOUT
    assert seen["start_new_session"] is True
    assert seen["close_fds"] is True
    assert (tmp_path / launch.SERVER_LOG_NAME).exists()


def test_real_subprocess_is_ready_before_browser_callback(
    monkeypatch, tmp_path: Path
) -> None:
    """Integration coverage: launch a real server and clean up its exact PID."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = int(listener.getsockname()[1])
    monkeypatch.setenv("LOCAL_PLANNER_DATA_DIR", str(tmp_path / "data"))
    opened: list[str] = []
    process: launch.Process | None = None
    try:
        url, started, process = launch.open_app(
            port, browser=opened.append, startup_timeout=5
        )
        assert started is True
        assert process is not None
        assert launch.service_is_ready(url)
        assert opened == [url]
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
