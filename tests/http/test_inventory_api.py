"""Inventory commands through the JSON adapter."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from local_planner.clock import FrozenClock
from local_planner.domain.commands import Planner
from local_planner.http.app import create_app
from local_planner.persistence import SqliteUnitOfWork

TODAY = "2026-08-30"
FUTURE = "2026-08-31"


def test_errand_never_appears_in_inventory(client: TestClient) -> None:
    created = client.post(f"/api/days/{TODAY}/errands", json={"title": "打印材料"})
    assert created.status_code == 200
    eid = created.json()["errands"][0]["id"]
    assert created.json()["errands"][0]["status"] == "open"
    assert client.get("/api/inventory").json()["items"] == []
    done = client.post(f"/api/errands/{eid}/complete")
    assert done.json()["errands"][0]["status"] == "completed"
    assert client.get("/api/inventory").json()["items"] == []
    client.post(f"/api/errands/{eid}/uncomplete")
    renamed = client.patch(f"/api/errands/{eid}", json={"title": "打印两份"})
    assert renamed.json()["errands"][0]["title"] == "打印两份"
    assert client.get("/api/inventory").json()["items"] == []
    deleted = client.delete(f"/api/errands/{eid}")
    assert deleted.status_code == 200
    assert deleted.json()["errands"] == []
    assert client.get("/api/inventory").json()["items"] == []


def test_add_to_inventory_does_not_appear_on_today(client: TestClient) -> None:
    created = client.post("/api/inventory/tasks", json={"title": "竞赛报名"})
    assert created.status_code == 200
    item = created.json()
    assert item["title"] == "竞赛报名"
    assert "taskId" in item
    assert item["createdAt"].endswith("Z")
    listed = client.get("/api/inventory").json()
    assert [row["taskId"] for row in listed["items"]] == [item["taskId"]]
    today = client.get(f"/api/days/{TODAY}").json()
    assert today["todos"] == []


def test_schedule_to_today_and_unschedule(client: TestClient) -> None:
    item = client.post("/api/inventory/tasks", json={"title": "抽出"}).json()
    tid = item["taskId"]
    scheduled = client.post(f"/api/tasks/{tid}/schedule", json={"date": TODAY})
    assert scheduled.status_code == 200
    assert scheduled.json()["todos"][0]["taskId"] == tid
    assert client.get("/api/inventory").json()["items"] == []
    back = client.post(f"/api/tasks/{tid}/unschedule")
    assert back.status_code == 200
    assert back.json()["taskId"] == tid
    assert [row["taskId"] for row in client.get("/api/inventory").json()["items"]] == [
        tid
    ]


def test_schedule_to_future(client: TestClient) -> None:
    item = client.post("/api/inventory/tasks", json={"title": "预排"}).json()
    tid = item["taskId"]
    future = client.post(f"/api/tasks/{tid}/schedule", json={"date": FUTURE})
    assert future.json()["date"] == FUTURE
    assert future.json()["todos"][0]["title"] == "预排"
    assert all(
        row["taskId"] != tid
        for row in client.get(f"/api/days/{TODAY}").json()["todos"]
    )


def test_rename_inventory_item(client: TestClient) -> None:
    item = client.post("/api/inventory/tasks", json={"title": "旧名"}).json()
    renamed = client.patch(f"/api/tasks/{item['taskId']}", json={"title": "新名"})
    assert renamed.status_code == 200
    assert renamed.json()["title"] == "新名"
    assert renamed.json()["taskId"] == item["taskId"]


def test_delete_task_without_history(client: TestClient) -> None:
    item = client.post("/api/inventory/tasks", json={"title": "误建"}).json()
    deleted = client.delete(f"/api/tasks/{item['taskId']}")
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True}
    assert client.get("/api/inventory").json()["items"] == []


def test_delete_task_with_sealed_history_conflicts(
    tmp_path: Path, clock: FrozenClock
) -> None:
    uow = SqliteUnitOfWork.open(tmp_path / "planner.sqlite")
    try:
        planner = Planner(clock=clock, uow=uow)
        with uow.transaction():
            plan = planner.add_todo_on_day(TODAY, "有历史")
            tid = plan.todos[0].task_id
            planner.seal_day(TODAY)
        with TestClient(
            create_app(
                clock=clock, uow=uow, port=8787, dev=False, data_dir=tmp_path
            ),
            base_url="http://127.0.0.1:8787",
        ) as client:
            response = client.delete(f"/api/tasks/{tid}")
            assert response.status_code == 409
            assert response.json()["error"] == "Conflict"
            assert "过去的某一天" in response.json()["message"]
    finally:
        uow.close()


def test_unknown_task_is_not_found(client: TestClient) -> None:
    response = client.post(
        "/api/tasks/00000000-0000-4000-8000-000000000000/schedule",
        json={"date": TODAY},
    )
    assert response.status_code == 404
    assert response.json()["error"] == "NotFound"
