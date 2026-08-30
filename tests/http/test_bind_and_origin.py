"""Bind 127.0.0.1 / workers=1, Origin 403, health skips settle."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from local_planner.clock import FrozenClock, SystemClock
from local_planner.domain.commands import Planner
from local_planner.http.app import PLANNER_LOCK, _locked, create_app, health
from local_planner.http.serve import serve, uvicorn_run_kwargs
from local_planner.paths import data_dir, resolve_clock
from local_planner.persistence import SqliteUnitOfWork
from local_planner.runtime import planner_txn

TODAY = "2026-08-30"
YESTERDAY = "2026-08-29"


def test_uvicorn_binds_loopback_single_worker() -> None:
    kwargs = uvicorn_run_kwargs(8787)
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["workers"] == 1
    assert kwargs["reload"] is False
    assert kwargs["port"] == 8787
    source = inspect.getsource(uvicorn_run_kwargs)
    assert '"127.0.0.1"' in source or "'127.0.0.1'" in source
    assert "0.0.0.0" not in source
    serve_src = inspect.getsource(serve)
    assert "0.0.0.0" not in serve_src
    assert "localhost" not in serve_src


def _fake_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir(exist_ok=True)
    (dist / "index.html").write_text(
        '<!doctype html><div id="root"></div>', encoding="utf-8"
    )
    return dist


def test_serve_passes_loopback_kwargs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_PLANNER_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("LOCAL_PLANNER_DEV", raising=False)
    monkeypatch.setattr(
        "local_planner.http.serve.resolve_web_dist", lambda: _fake_dist(tmp_path)
    )
    seen: dict = {}

    def fake_run(app, **kwargs):
        seen.update(kwargs)
        seen["_app"] = app

    monkeypatch.setattr("local_planner.http.serve.uvicorn.run", fake_run)
    serve()
    assert seen["host"] == "127.0.0.1"
    assert seen["workers"] == 1
    assert seen["reload"] is False
    assert seen["port"] == 8787
    with TestClient(seen["_app"], base_url="http://127.0.0.1:8787") as client:
        page = client.get("/inventory")
        assert page.status_code == 200
        assert "text/html" in page.headers.get("content-type", "")
        assert 'id="root"' in page.text


def _client(app) -> TestClient:
    return TestClient(app, base_url="http://127.0.0.1:8787")


def test_mutating_malicious_origin_is_403(client: TestClient) -> None:
    response = client.post(
        "/api/inventory/tasks",
        json={"title": "不该写入"},
        headers={"Origin": "http://evil.example"},
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"] == "Forbidden"
    listed = client.get("/api/inventory").json()["items"]
    assert listed == []
    acao = response.headers.get("access-control-allow-origin")
    assert acao is None or acao != "*"


def test_mutating_empty_origin_allowed(client: TestClient) -> None:
    response = client.post("/api/inventory/tasks", json={"title": "curl 写入"})
    assert response.status_code == 200
    assert response.json()["title"] == "curl 写入"


def test_mutating_loopback_origin_allowed(client: TestClient) -> None:
    response = client.post(
        "/api/inventory/tasks",
        json={"title": "同源"},
        headers={"Origin": "http://127.0.0.1:8787"},
    )
    assert response.status_code == 200


def test_vite_origin_only_in_dev(
    clock: FrozenClock, uow: SqliteUnitOfWork, tmp_path: Path
) -> None:
    with _client(
        create_app(clock=clock, uow=uow, port=8787, dev=False, data_dir=tmp_path)
    ) as prod:
        denied = prod.post(
            "/api/inventory/tasks",
            json={"title": "vite"},
            headers={"Origin": "http://127.0.0.1:5173"},
        )
        assert denied.status_code == 403
    with _client(
        create_app(clock=clock, uow=uow, port=8787, dev=True, data_dir=tmp_path)
    ) as dev:
        allowed = dev.post(
            "/api/inventory/tasks",
            json={"title": "vite"},
            headers={"Origin": "http://127.0.0.1:5173"},
        )
        assert allowed.status_code == 200
        localhost = dev.post(
            "/api/inventory/tasks",
            json={"title": "vite-localhost"},
            headers={"Origin": "http://localhost:5173"},
        )
        assert localhost.status_code == 200


def test_cors_never_star(client: TestClient) -> None:
    response = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") != "*"


def test_health_skips_settle(tmp_path: Path) -> None:
    clock = FrozenClock("2026-08-29T12:00:00+08:00")
    uow = SqliteUnitOfWork.open(tmp_path / "planner.sqlite")
    try:
        planner = Planner(clock=clock, uow=uow)
        with uow.transaction():
            plan = planner.add_errand(YESTERDAY, "过夜差事")
            eid = plan.errands[0].id
        clock.set("2026-08-30T12:00:00+08:00")
        with _client(
            create_app(
                clock=clock, uow=uow, port=8787, dev=False, data_dir=tmp_path
            )
        ) as client:
            health_response = client.get("/api/health")
            assert health_response.status_code == 200
            assert health_response.json() == {"ok": True}
            assert uow.get_day(YESTERDAY).status == "open"
            assert uow.get_errand(eid).status == "open"
            meta = client.get("/api/meta")
            assert meta.status_code == 200
            assert meta.json()["today"] == TODAY
            assert uow.get_day(YESTERDAY).status == "sealed"
            assert uow.get_errand(eid).status == "expired"
    finally:
        uow.close()


def test_health_source_has_no_lock_or_settle() -> None:
    source = inspect.getsource(health)
    assert "ensure_settled" not in source
    assert "PLANNER_LOCK" not in source
    assert "interprocess_lock" not in source
    assert "transaction" not in source


def test_locked_path_is_lock_then_transaction_then_settle() -> None:
    source = inspect.getsource(_locked)
    assert "PLANNER_LOCK" in source
    assert source.index("PLANNER_LOCK") < source.index("interprocess_lock")
    txn_src = inspect.getsource(planner_txn)
    assert (
        txn_src.index("transaction()")
        < txn_src.index("ensure_settled")
        < txn_src.index("clock.today()")
    )
    assert type(PLANNER_LOCK).__name__ == "lock"


def test_api_routes_are_sync_def(app) -> None:
    for route in app.routes:
        path = getattr(route, "path", "")
        endpoint = getattr(route, "endpoint", None)
        if path.startswith("/api") and endpoint is not None:
            assert not inspect.iscoroutinefunction(endpoint), path


def test_unknown_api_is_json_404(client: TestClient) -> None:
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "NotFound"
    assert "application/json" in response.headers.get("content-type", "")


def test_serve_production_missing_dist_exits(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setenv("LOCAL_PLANNER_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("LOCAL_PLANNER_DEV", raising=False)
    monkeypatch.setattr("local_planner.http.serve.resolve_web_dist", lambda: None)
    monkeypatch.setattr("local_planner.http.serve.uvicorn.run", lambda *a, **k: None)
    with pytest.raises(SystemExit) as excinfo:
        serve()
    assert excinfo.value.code == 1
    assert "npm run build" in capsys.readouterr().err


def test_serve_dev_without_dist_starts_api(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_PLANNER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LOCAL_PLANNER_DEV", "1")
    monkeypatch.setattr("local_planner.http.serve.resolve_web_dist", lambda: None)
    seen: dict = {}

    def fake_run(app, **kwargs):
        seen.update(kwargs)
        seen["_app"] = app

    monkeypatch.setattr("local_planner.http.serve.uvicorn.run", fake_run)
    serve()
    assert seen["host"] == "127.0.0.1"
    with TestClient(seen["_app"], base_url="http://127.0.0.1:8787") as client:
        response = client.get("/inventory")
        assert response.status_code == 404
        assert response.json()["error"] == "NotFound"


def test_clock_override_requires_allow_flag(monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_PLANNER_CLOCK", "2026-08-30T12:00:00+08:00")
    monkeypatch.delenv("LOCAL_PLANNER_ALLOW_CLOCK_OVERRIDE", raising=False)
    clock = resolve_clock()
    assert isinstance(clock, SystemClock)
    monkeypatch.setenv("LOCAL_PLANNER_ALLOW_CLOCK_OVERRIDE", "1")
    frozen = resolve_clock()
    assert frozen.today() == TODAY


def test_data_dir_override_and_default(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCAL_PLANNER_DATA_DIR", str(tmp_path))
    assert data_dir() == tmp_path
    monkeypatch.delenv("LOCAL_PLANNER_DATA_DIR")
    monkeypatch.delenv("LOCAL_PLANNER_DEV", raising=False)
    assert data_dir() == (
        Path.home() / "Library" / "Application Support" / "local-planner"
    )
