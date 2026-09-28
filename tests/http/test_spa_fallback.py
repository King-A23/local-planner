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
    clock: FrozenClock, uow: SqliteUnitOfWork, spa_dist: Path, tmp_path: Path
) -> Iterator[TestClient]:
    app = create_app(
        clock=clock,
        uow=uow,
        port=8787,
        dev=False,
        dist_dir=spa_dist,
        data_dir=tmp_path,
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
    assert "今日计划" in day_view
    assert "<h2>零碎事项</h2>" in day_view
    files = list(src.rglob("*.ts")) + list(src.rglob("*.tsx"))
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "new Date()" not in text, path
        assert "new Date(" not in text, path


def test_day_view_has_errand_column_not_on_inventory() -> None:
    web = Path(__file__).resolve().parents[2] / "web"
    src = web / "src"
    api = (src / "api.ts").read_text(encoding="utf-8")
    day_view = (src / "DayView.tsx").read_text(encoding="utf-8")
    app = (src / "App.tsx").read_text(encoding="utf-8")
    assert "<h2>零碎事项</h2>" in day_view
    assert "已作废" in day_view
    assert "addErrandOnDay" in day_view
    assert "completeErrand" in day_view
    assert "uncompleteErrand" in day_view
    assert "deleteErrand" in day_view
    assert "/api/days/${date}/errands" in api
    assert "/api/errands/${errandId}/complete" in api
    assert "/api/calendar" not in day_view
    assert "ListInventory" not in day_view
    assert "零碎差事" not in app
    assert "<h2>零碎事项</h2>" not in app
    assert "<h2>零碎事项</h2>" not in app
    assert "InventoryPage" in app
    assert "未排期的正经待办将出现在这里" not in app


def test_date_nav_calendar_readonly_and_midnight_poll() -> None:
    web = Path(__file__).resolve().parents[2] / "web"
    src = web / "src"
    dates = (src / "dates.ts").read_text(encoding="utf-8")
    api = (src / "api.ts").read_text(encoding="utf-8")
    app = (src / "App.tsx").read_text(encoding="utf-8")
    shell = (src / "Shell.tsx").read_text(encoding="utf-8")
    day_view = (src / "DayView.tsx").read_text(encoding="utf-8")
    calendar = (src / "Calendar.tsx").read_text(encoding="utf-8")
    constants = (src / "constants.ts").read_text(encoding="utf-8")

    assert "export function addCivilDays" in dates
    assert "daysInMonth" in dates
    assert "new Date" not in dates
    assert "slice(" not in dates

    assert "getCalendar" in api
    assert "/api/calendar?" in api
    assert "todoCount" in api
    assert "errandCount" in api

    assert "addCivilDays(plan.date, -1)" in day_view
    assert "addCivilDays(plan.date, 1)" in day_view
    assert 'aria-label="上一天"' in day_view
    assert 'aria-label="下一天"' in day_view
    assert 'className="day-columns"' in day_view
    assert 'className="column-empty"' in day_view
    assert "DaySealed" in day_view
    assert "这是过去的记录，仅供回看。" in day_view
    assert "page readonly" in day_view
    assert "[date, serverToday, refreshToken]" in day_view
    assert "/api/calendar" not in day_view
    assert "ListInventory" not in day_view

    assert "META_POLL_MS = 30_000" in constants
    assert "setInterval" in app
    assert "META_POLL_MS" in app
    assert "getMeta" in app
    assert 'navigate("/planning/today")' in app
    assert "history.pushState" not in app
    assert "history.replaceState" not in app
    assert "serverToday={meta?.today}" in app
    assert "serverToday={meta.today}" in app
    assert "if (!meta)" in app
    assert "if (metaError)" not in app
    assert "§" not in app
    assert "§" not in constants
    assert "§" not in dates

    assert "MonthCalendar" in shell
    assert 'aria-current={activeSection === "today" ? "page" : undefined}' in shell
    assert 'aria-current={activeSection === "inventory" ? "page" : undefined}' in shell
    assert 'aria-current={activeSection === "recurrences" ? "page" : undefined}' in shell
    assert 'handleNavClick(e, "/")' in shell
    assert "todoCount + day.errandCount > 0" in calendar
    assert "navigate(`/d/${date}`)" in calendar
    assert 'navigate("/")' in calendar
    assert "getCalendar(from, to)" in calendar


def test_inventory_schedule_and_inline_add_ui() -> None:
    web = Path(__file__).resolve().parents[2] / "web"
    src = web / "src"
    constants = (src / "constants.ts").read_text(encoding="utf-8")
    api = (src / "api.ts").read_text(encoding="utf-8")
    app = (src / "App.tsx").read_text(encoding="utf-8")
    day_view = (src / "DayView.tsx").read_text(encoding="utf-8")
    inventory = (src / "InventoryPage.tsx").read_text(encoding="utf-8")
    date_pick = (src / "DatePickButton.tsx").read_text(encoding="utf-8")

    assert "INVENTORY_INLINE_LIMIT = 8" in constants
    assert "listInventory" in api
    assert "/api/inventory/tasks" in api
    assert "/api/tasks/${taskId}/schedule" in api
    assert "/api/tasks/${taskId}/unschedule" in api

    assert "InventoryPage" in app
    assert "onInventoryChange={refreshMeta}" in app

    assert "从待办中挑选" in day_view
    assert "Add" in day_view
    assert "查看全部待办 →" in day_view
    assert 'handleNavClick(event, "/inventory")' in day_view
    assert "移回待办" in day_view
    assert "Reschedule" not in day_view
    assert "INVENTORY_INLINE_LIMIT" in day_view
    assert "items.slice(0, INVENTORY_INLINE_LIMIT)" in day_view
    assert "plan.writable" in day_view
    assert "[date, plan?.writable, serverToday, refreshToken]" in day_view
    assert "scheduleTask(item.taskId, plan.date)" in day_view
    assert 'role="dialog"' not in day_view
    assert "modal" not in day_view.lower()

    assert "<h1>待办</h1>" in inventory
    assert "加入今天" in inventory
    assert 'label="安排到某天"' in inventory
    assert "addToInventory" in inventory
    assert "scheduleTask" in inventory
    assert "inventory-composer-title" in inventory
    assert "先记下来，以后再安排" in inventory
    assert 'placeholder="输入待办事项，按回车添加"' in inventory
    assert "formatChineseDate(draftDate)" in inventory
    assert 'return "选择日期"' in inventory
    assert "年${Number(month)}月${Number(day)}日" in inventory
    assert 'lang="zh-CN"' in inventory
    assert "inventory-add-form" in inventory
    assert "inventory-add-button" in inventory
    assert "disabled={!draft.trim()}" in inventory
    assert 'role="dialog"' not in inventory
    assert "零碎差事" not in inventory
    assert "<h2>零碎事项</h2>" not in inventory
    assert "errand" not in inventory.lower()
    assert "new Date(" not in inventory
    assert "new Date(" not in date_pick
    assert 'type="date"' in date_pick
    assert 'role="dialog"' not in date_pick


def test_reorder_ui_uses_existing_order_apis() -> None:
    web = Path(__file__).resolve().parents[2] / "web"
    src = web / "src"
    api = (src / "api.ts").read_text(encoding="utf-8")
    day_view = (src / "DayView.tsx").read_text(encoding="utf-8")
    inventory = (src / "InventoryPage.tsx").read_text(encoding="utf-8")

    assert "reorderTodos" in api
    assert "reorderErrands" in api
    assert "/api/days/${date}/todos/order" in api
    assert "/api/days/${date}/errands/order" in api
    assert 'aria-label="Move up"' not in day_view
    assert 'aria-label="Move down"' not in day_view
    assert "onMoveTodo" not in day_view
    assert "onMoveErrand" not in day_view
    assert "reorderTodos" not in inventory
    assert "reorderErrands" not in inventory


def test_v2_clocks_and_agent_panel_ui() -> None:
    web = Path(__file__).resolve().parents[2] / "web"
    src = web / "src"
    day_view = (src / "DayView.tsx").read_text(encoding="utf-8")
    inventory = (src / "InventoryPage.tsx").read_text(encoding="utf-8")
    app = (src / "App.tsx").read_text(encoding="utf-8")
    clock = (src / "ClockField.tsx").read_text(encoding="utf-8")
    agent = (src / "AgentPanel.tsx").read_text(encoding="utf-8")
    api = (src / "api.ts").read_text(encoding="utf-8")

    assert "ClockField" in day_view
    assert 'label="开始"' in day_view
    assert 'label="结束"' in day_view
    assert 'type="range"' not in clock
    assert "SLOT_COUNT" not in clock
    assert "new Date(" not in clock
    assert "目标日已过" in inventory
    assert "目标日是今天" in inventory
    assert 'aria-label="目标日期（不会自动排入当天）"' in inventory
    assert "setTaskTarget" in inventory
    planning = (src / "DailyPlanningPage.tsx").read_text(encoding="utf-8")
    assert "AgentPanel" in app
    assert "AgentPanel" not in planning
    assert "planTick" not in app
    assert "onOpenAgent" in planning
    assert 'className="layout"' in app
    shell = (src / "Shell.tsx").read_text(encoding="utf-8")
    styles = (src / "styles.css").read_text(encoding="utf-8")
    assert "agent-drawer" in agent
    assert 'role="dialog"' not in agent
    assert 'hidden={!open}' in agent
    assert "aria-expanded={agentOpen}" in planning
    assert "nav-agent" in shell
    assert "onOpenAgent" in shell
    assert "agent-run-controls" in agent
    assert 'event.key === "Escape"' in agent
    assert "@media (max-width: 30rem)" in styles
    assert 'aria-label="选择计划助手"' in agent
    assert "opencode run {prompt}" not in agent
    assert "agent-output" in agent
    assert "result?.stdout" in agent
    assert "删除" in agent
    assert "/api/launchers" in agent
    assert "/api/agent-runs" in agent
    assert "重新执行" not in agent
    assert "setPrompt(\"\")" not in agent
    assert "resubmit" not in agent
    assert "surface," in agent
    assert "date," in agent
    assert "setTodoClocks" in api
    assert "setErrandClocks" in api
    assert "/api/tasks/${taskId}/target" in api


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
