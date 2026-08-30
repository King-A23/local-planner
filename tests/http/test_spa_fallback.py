"""SPA fallback: non-API GET returns index.html; /api stays JSON."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from local_planner.clock import FrozenClock
from local_planner.http.app import create_app
from local_planner.http.spa import resolve_web_dist, web_dist_candidates
from local_planner.persistence import SqliteUnitOfWork

INDEX = "<!doctype html><html><body><div id=\"root\"></div></body></html>"


@pytest.fixture
def spa_dist(tmp_path: Path) -> Path:
    dist = tmp_path / "spa-dist"
    dist.mkdir()
    (dist / "index.html").write_text(INDEX, encoding="utf-8")
    assets = dist / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("console.log('ok');\n", encoding="utf-8")
    return dist


@pytest.fixture
def spa_client(
    clock: FrozenClock, uow: SqliteUnitOfWork, spa_dist: Path
) -> Iterator[TestClient]:
    app = create_app(
        clock=clock, uow=uow, port=8787, dev=False, dist_dir=spa_dist
    )
    with TestClient(app, base_url="http://127.0.0.1:8787") as client:
        yield client


def _assert_spa_html(response) -> None:
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert 'id="root"' in response.text
    assert response.headers.get("content-security-policy") == "default-src 'self'"


def test_get_inventory_returns_spa_html(spa_client: TestClient) -> None:
    _assert_spa_html(spa_client.get("/inventory"))


def test_get_day_path_returns_spa_html(spa_client: TestClient) -> None:
    _assert_spa_html(spa_client.get("/d/2026-08-30"))


def test_get_root_returns_spa_html(spa_client: TestClient) -> None:
    _assert_spa_html(spa_client.get("/"))


def test_unknown_api_stays_json_404(spa_client: TestClient) -> None:
    response = spa_client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert "application/json" in response.headers.get("content-type", "")
    body = response.json()
    assert body["error"] == "NotFound"
    assert "detail" not in body


def test_api_inventory_still_json(spa_client: TestClient) -> None:
    response = spa_client.get("/api/inventory")
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_open_day_api_still_json(spa_client: TestClient) -> None:
    response = spa_client.get("/api/days/2026-08-30")
    assert response.status_code == 200
    body = response.json()
    assert body["date"] == "2026-08-30"
    assert body["writable"] is True
    assert body["todos"] == []


def test_spa_serves_real_asset(spa_client: TestClient) -> None:
    response = spa_client.get("/assets/app.js")
    assert response.status_code == 200
    assert "console.log('ok')" in response.text


def test_spa_does_not_leak_outside_dist(spa_client: TestClient) -> None:
    response = spa_client.get("/../pyproject.toml")
    assert response.status_code == 200
    assert 'id="root"' in response.text
    assert "name = " not in response.text


def test_frontend_does_not_use_utc_date_strings() -> None:
    web = Path(__file__).resolve().parents[2] / "web"
    src = web / "src"
    constants = (src / "constants.ts").read_text(encoding="utf-8")
    assert 'DISPLAY_NAME = "Local Planner"' in constants
    assert "Local Planner" not in (web / "index.html").read_text(encoding="utf-8")
    vite = (web / "vite.config.ts").read_text(encoding="utf-8")
    assert "src/constants.ts" in vite
    assert "transformIndexHtml" in vite
    day_view = (src / "DayView.tsx").read_text(encoding="utf-8")
    assert "回车即加入今天" in day_view
    assert "回车即加入这一天" in day_view
    files = list(src.rglob("*.ts")) + list(src.rglob("*.tsx"))
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "new Date()" not in text, path
        assert "new Date(" not in text, path


def _write_index(path: Path, body: str = "ok") -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "index.html").write_text(body, encoding="utf-8")
    return path


def test_web_dist_stops_at_pyproject_and_ignores_strays(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    here = repo / "src" / "local_planner" / "http" / "spa.py"
    here.parent.mkdir(parents=True)
    here.write_text("", encoding="utf-8")
    (repo / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    good = _write_index(repo / "web" / "dist", "repo")
    stray = _write_index(tmp_path / "web" / "dist", "stray")

    candidates = [p.resolve() for p in web_dist_candidates(here)]
    assert good.resolve() in candidates
    assert stray.resolve() not in candidates
    found = resolve_web_dist(here=here)
    assert found is not None
    assert found.resolve() == good.resolve()
    assert (found / "index.html").read_text(encoding="utf-8") == "repo"


def test_web_dist_missing_repo_copy_does_not_use_ancestor_stray(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    here = repo / "src" / "local_planner" / "http" / "spa.py"
    here.parent.mkdir(parents=True)
    here.write_text("", encoding="utf-8")
    (repo / "pyproject.toml").write_text("[project]\nname = 'x'\n", encoding="utf-8")
    _write_index(tmp_path / "web" / "dist", "stray")
    assert resolve_web_dist(here=here) is None


def test_web_dist_packaged_next_to_package_without_pyproject(
    tmp_path: Path,
) -> None:
    here = tmp_path / "site-packages" / "local_planner" / "http" / "spa.py"
    here.parent.mkdir(parents=True)
    here.write_text("", encoding="utf-8")
    packaged = _write_index(
        tmp_path / "site-packages" / "local_planner" / "web" / "dist", "pkg"
    )
    _write_index(tmp_path / "web" / "dist", "stray")
    found = resolve_web_dist(here=here)
    assert found is not None
    assert found.resolve() == packaged.resolve()
    assert (found / "index.html").read_text(encoding="utf-8") == "pkg"
