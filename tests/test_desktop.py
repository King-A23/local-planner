"""Desktop integration: the real server, isolated data, and owned processes."""

from __future__ import annotations

import json
import os
import socket
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from local_planner import launchers
from local_planner.desktop import bind_listener


@pytest.mark.skipif(sys.platform != "darwin" or not shutil.which("xcrun"), reason="requires the macOS Swift compiler")
def test_native_navigation_interruption_does_not_hide_real_failures(tmp_path):
    root = Path(__file__).resolve().parents[1]
    executable = tmp_path / "navigation-failure-checks"
    subprocess.run(
        ["xcrun", "swiftc", "-swift-version", "5",
         str(root / "desktop/macos/NavigationFailure.swift"),
         str(root / "tests/desktop/navigation_failure_checks.swift"),
         "-o", str(executable)],
        capture_output=True, text=True, check=True, timeout=60,
    )
    result = subprocess.run([str(executable)], capture_output=True, text=True, check=True, timeout=10)
    assert "8 navigation failure checks passed" in result.stdout


@contextmanager
def desktop_server(root: Path, port: int = 0):
    log_path = root / "output.log"
    with log_path.open("w") as log:
        process = subprocess.Popen(
            [sys.executable, "-m", "local_planner.desktop", "desktop-serve", "--port", str(port)],
            cwd=root, env={**os.environ, "LOCAL_PLANNER_DATA_DIR": str(root / "data")},
            stdin=subprocess.PIPE, stdout=log, stderr=log,
        )
        try:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                assert process.poll() is None, log_path.read_text()
                for line in log_path.read_text().splitlines():
                    if line.startswith('{"event": "ready"'):
                        yield process, json.loads(line)["url"]
                        return
                time.sleep(0.05)
            pytest.fail(log_path.read_text())
        finally:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            try:
                process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
                pytest.fail("desktop backend survived parent pipe closure")


def test_real_desktop_serves_spa_shares_cli_data_and_exits_on_parent_eof(tmp_path):
    with desktop_server(tmp_path) as (process, url):
        with httpx.Client(base_url=url, trust_env=False) as client:
            assert client.get("api/health").json()["ok"] is True
            assert 'id="root"' in client.get("inventory").text
            created = client.post("api/inventory/tasks", json={"title": "桌面测试"}, headers={"Origin": url.rstrip("/")})
            assert created.status_code == 200
            assert client.post("api/inventory/tasks", json={"title": "拒绝外站"}, headers={"Origin": "https://example.com"}).status_code == 403
        completed = subprocess.run(
            [sys.executable, "-m", "local_planner", "inventory", "list"],
            cwd=tmp_path, env={**os.environ, "LOCAL_PLANNER_DATA_DIR": str(tmp_path / "data")},
            capture_output=True, text=True, check=True,
        )
        assert "桌面测试" in completed.stdout
        port = int(url.split(":")[-1].strip("/"))
    assert process.poll() is not None
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=0.1)
    with desktop_server(tmp_path) as (_, url):
        assert httpx.get(url + "api/inventory", trust_env=False).json()["items"][0]["title"] == "桌面测试"


def test_busy_desktop_port_uses_own_service_and_leaves_existing_listener(tmp_path):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as existing:
        existing.bind(("127.0.0.1", 0))
        existing.listen()
        port = existing.getsockname()[1]
        with desktop_server(tmp_path, port) as (_, url):
            assert url != f"http://127.0.0.1:{port}/"
            assert httpx.get(url + "api/health", trust_env=False).is_success
        with socket.create_connection(("127.0.0.1", port), timeout=0.1):
            pass


def test_listener_is_ipv4_numeric_loopback():
    with bind_listener(0) as listener:
        assert listener.family == socket.AF_INET
        assert listener.getsockname()[0] == "127.0.0.1"


def test_frozen_agent_cli_uses_executable_without_python_module_flags(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/Applications/Local Planner.app/Contents/Resources/backend/local-planner-backend")
    assert launchers.cli_argv() == [sys.executable]


def test_agent_process_group_is_stopped_on_shutdown(tmp_path):
    # Isolate the permanent shutdown flag from other launcher tests.
    script = '''
import sys, subprocess
from local_planner.processes import agent_process, stop_agents
with agent_process([sys.executable, "-c", "import time; time.sleep(120)"], stdout=subprocess.PIPE) as process:
    print(process.pid, flush=True)
    stop_agents()
    process.wait(timeout=3)
    assert process.returncode != 0
try:
    with agent_process([sys.executable, "-c", "pass"]):
        raise AssertionError("must not start after shutdown")
except OSError:
    pass
'''
    result = subprocess.run([sys.executable, "-c", script], cwd=tmp_path, capture_output=True, text=True, timeout=10, check=True)
    with pytest.raises(ProcessLookupError):
        os.kill(int(result.stdout.strip()), 0)
