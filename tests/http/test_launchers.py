"""User-defined launchers through HTTP, including a real stub process."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient

STUB = Path(__file__).resolve().parents[1] / "launchers" / "echo_stub.py"


def test_launchers_crud_and_default_opencode(client: TestClient) -> None:
    listed = client.get("/api/launchers")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert any(
        item["command"].startswith("opencode") and "{prompt}" in item["command"]
        for item in items
    )
    created = client.post(
        "/api/launchers",
        json={"name": "Echo", "command": "echo {prompt}"},
    )
    assert created.status_code == 200
    lid = created.json()["id"]
    patched = client.patch(
        f"/api/launchers/{lid}",
        json={"name": "Echo 2", "command": "echo hi {prompt}"},
    )
    assert patched.json()["name"] == "Echo 2"
    empty = client.post("/api/launchers", json={"name": "  ", "command": "echo"})
    assert empty.status_code == 400
    deleted = client.delete(f"/api/launchers/{lid}")
    assert deleted.status_code == 200
    remaining = {item["id"] for item in client.get("/api/launchers").json()["items"]}
    assert lid not in remaining


def test_run_launcher_http_passes_prompt_and_context(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    proof = tmp_path / "proof.json"
    monkeypatch.setenv("LAUNCHER_PROOF", str(proof))
    created = client.post(
        "/api/launchers",
        json={
            "name": "Stub",
            "command": f"{sys.executable} {STUB} {{prompt}}",
        },
    )
    lid = created.json()["id"]
    ran = client.post(
        f"/api/launchers/{lid}/run",
        json={"prompt": "list today and add an errand"},
    )
    assert ran.status_code == 200
    body = ran.json()
    assert body["ok"] is True
    assert body["stdout"].strip() == "stub-ok"
    recorded = json.loads(proof.read_text(encoding="utf-8"))
    assert recorded["prompt"].endswith("list today and add an errand")
    assert "不要写 endClock" in recorded["prompt"]
    assert "list today and add an errand" in recorded["argv"][-1]
    context = json.loads(recorded["context"])
    assert context["today"] == "2026-08-30"
    assert "todos" in context
    assert "inventory" in context


def test_run_launcher_returns_structured_receipt_for_cli_changes(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/launchers",
        json={
            "name": "Add through CLI",
            "command": (
                f"{sys.executable} -m local_planner inventory add "
                "--title agent-added"
            ),
        },
    )
    lid = created.json()["id"]

    ran = client.post(
        f"/api/launchers/{lid}/run",
        json={"prompt": "add one todo"},
    )

    assert ran.status_code == 200
    body = ran.json()
    assert body["ok"] is True
    assert body["status"] == "succeeded"
    assert body["receipt"]["changed"] is True
    assert body["receipt"]["counts"] == {"todo_added": 1}
    assert body["receipt"]["changes"][0]["title"] == "agent-added"


def test_run_launcher_receipt_includes_future_errand(
    client: TestClient, monkeypatch
) -> None:
    # The launcher runs in a child process, so pin it to the fixture's calendar too.
    monkeypatch.setenv("LOCAL_PLANNER_CLOCK", "2026-08-30T12:00:00+08:00")
    monkeypatch.setenv("LOCAL_PLANNER_ALLOW_CLOCK_OVERRIDE", "1")
    created = client.post(
        "/api/launchers",
        json={
            "name": "Add future errand",
            "command": (
                f"{sys.executable} -m local_planner day errand add "
                "2026-09-01 --title future-errand"
            ),
        },
    )
    ran = client.post(
        f"/api/launchers/{created.json()['id']}/run",
        json={"prompt": "add a future errand"},
    )
    assert ran.status_code == 200
    receipt = ran.json()["receipt"]
    assert receipt["counts"] == {"errand_added": 1}
    assert receipt["changes"][0]["date"] == "2026-09-01"


def test_timeout_after_write_returns_partial_receipt(client, tmp_path, monkeypatch):
    import shlex
    import local_planner.http.app as app_module
    from local_planner.launchers import run_launcher

    monkeypatch.setenv("LOCAL_PLANNER_CLOCK", "2026-08-30T12:00:00+08:00")
    monkeypatch.setenv("LOCAL_PLANNER_ALLOW_CLOCK_OVERRIDE", "1")
    original = run_launcher

    def short_run(*args, **kwargs):
        kwargs["timeout"] = 1
        return original(*args, **kwargs)

    monkeypatch.setattr(app_module, "run_launcher", short_run)
    stub = tmp_path / "partial.py"
    stub.write_text('''import subprocess, sys, time
subprocess.run([sys.executable, "-m", "local_planner", "inventory", "add", "--title", "partial"], check=True)
print("已写入", flush=True)
time.sleep(60)
''')
    created = client.post("/api/launchers", json={
        "name": "Partial", "command": shlex.join([sys.executable, str(stub)])
    })
    ran = client.post(f"/api/launchers/{created.json()['id']}/run", json={"prompt": "test"})
    assert ran.status_code == 200
    body = ran.json()
    assert body["status"] == "failed_with_changes"
    assert body["receipt"]["counts"] == {"todo_added": 1}
    assert "timeout" in body["stderr"]
    assert "已写入" in body["stdout"]
