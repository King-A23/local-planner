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
    assert deleted.json()["ok"] is True
    assert deleted.json()["undo"]["token"]
    assert client.get("/api/inventory").json()["items"] == []


def test_delete_task_from_todo_keeps_sealed_snapshot(
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
            listed = client.get("/api/inventory").json()["items"]
            assert [row["taskId"] for row in listed] == [tid]
            response = client.delete(f"/api/tasks/{tid}")
            assert response.status_code == 200
            assert client.get("/api/inventory").json()["items"] == []
            past = client.get(f"/api/days/{TODAY}").json()
            assert past["todos"][0]["taskId"] == tid
            assert past["todos"][0]["title"] == "有历史"
    finally:
        uow.close()


def test_unknown_task_is_not_found(client: TestClient) -> None:
    response = client.post(
        "/api/tasks/00000000-0000-4000-8000-000000000000/schedule",
        json={"date": TODAY},
    )
    assert response.status_code == 404
    assert response.json()["error"] == "NotFound"


def test_complete_inventory_task_preserves_today_history(client: TestClient) -> None:
    task = client.post('/api/inventory/tasks', json={'title': '直接完成'}).json()
    tid = task['taskId']
    done = client.post(f'/api/inventory/tasks/{tid}/complete')
    assert done.status_code == 200
    row = next(row for row in done.json()['todos'] if row['taskId'] == tid)
    assert row['completedOnDay'] is True
    assert row['startClock'] is None and row['endClock'] is None
    assert client.get('/api/inventory').json()['items'] == []
    assert client.post(f'/api/inventory/tasks/{tid}/complete').status_code == 409
    assert client.post(f'/api/days/{TODAY}/todos/{tid}/uncomplete').status_code == 200


def test_complete_inventory_rejects_stale_scheduled_task(client: TestClient) -> None:
    task = client.post('/api/inventory/tasks', json={'title': '已排期'}).json()
    tid = task['taskId']
    client.post(f'/api/tasks/{tid}/schedule', json={'date': FUTURE})
    assert client.post(f'/api/inventory/tasks/{tid}/complete').status_code == 409
    assert client.get(f'/api/days/{TODAY}').json()['todos'] == []
    assert client.get(f'/api/days/{FUTURE}').json()['todos'][0]['taskId'] == tid
