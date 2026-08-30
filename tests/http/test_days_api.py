"""Day reads/writes, calendar, reorder, errands on a writable day."""

from __future__ import annotations

from fastapi.testclient import TestClient

TODAY = "2026-08-30"
FUTURE = "2026-08-31"


def test_open_today_is_writable_camel_case(client: TestClient) -> None:
    response = client.get(f"/api/days/{TODAY}")
    assert response.status_code == 200
    body = response.json()
    assert body["date"] == TODAY
    assert body["serverToday"] == TODAY
    assert body["isToday"] is True
    assert body["isPast"] is False
    assert body["isFuture"] is False
    assert body["writable"] is True
    assert body["status"] == "open"
    assert body["todos"] == []
    assert body["errands"] == []
    assert "sealed_at" not in body
    assert "server_today" not in body


def test_add_complete_uncomplete_todo(client: TestClient) -> None:
    created = client.post(f"/api/days/{TODAY}/todos", json={"title": "把设计文档写完"})
    assert created.status_code == 200
    todo = created.json()["todos"][0]
    tid = todo["taskId"]
    assert todo["title"] == "把设计文档写完"
    assert todo["completedOnDay"] is False
    assert todo["sortOrder"] == 0
    inv = client.get("/api/inventory").json()["items"]
    assert inv == []
    completed = client.post(f"/api/days/{TODAY}/todos/{tid}/complete")
    assert completed.status_code == 200
    assert completed.json()["todos"][0]["completedOnDay"] is True
    undone = client.post(f"/api/days/{TODAY}/todos/{tid}/uncomplete")
    assert undone.json()["todos"][0]["completedOnDay"] is False


def test_future_day_complete_sets_plan_date(client: TestClient) -> None:
    created = client.post(f"/api/days/{FUTURE}/todos", json={"title": "未来勾"})
    tid = created.json()["todos"][0]["taskId"]
    done = client.post(f"/api/days/{FUTURE}/todos/{tid}/complete")
    assert done.status_code == 200
    assert done.json()["date"] == FUTURE
    assert done.json()["todos"][0]["completedOnDay"] is True
    assert done.json()["isFuture"] is True


def test_add_complete_errand_and_rename(client: TestClient) -> None:
    created = client.post(f"/api/days/{TODAY}/errands", json={"title": "打印材料"})
    assert created.status_code == 200
    eid = created.json()["errands"][0]["id"]
    renamed = client.patch(f"/api/errands/{eid}", json={"title": "打印两份"})
    assert renamed.json()["errands"][0]["title"] == "打印两份"
    done = client.post(f"/api/errands/{eid}/complete")
    assert done.json()["errands"][0]["status"] == "completed"
    undone = client.post(f"/api/errands/{eid}/uncomplete")
    assert undone.json()["errands"][0]["status"] == "open"
    assert client.get("/api/inventory").json()["items"] == []


def test_reorder_todos_and_errands(client: TestClient) -> None:
    client.post(f"/api/days/{TODAY}/todos", json={"title": "A"})
    client.post(f"/api/days/{TODAY}/todos", json={"title": "B"})
    ids = [item["taskId"] for item in client.get(f"/api/days/{TODAY}").json()["todos"]]
    reordered = client.put(
        f"/api/days/{TODAY}/todos/order", json={"taskIds": list(reversed(ids))}
    )
    assert [item["title"] for item in reordered.json()["todos"]] == ["B", "A"]
    client.post(f"/api/days/{TODAY}/errands", json={"title": "E1"})
    client.post(f"/api/days/{TODAY}/errands", json={"title": "E2"})
    eids = [item["id"] for item in client.get(f"/api/days/{TODAY}").json()["errands"]]
    errands = client.put(
        f"/api/days/{TODAY}/errands/order", json={"errandIds": list(reversed(eids))}
    )
    assert [item["title"] for item in errands.json()["errands"]] == ["E2", "E1"]


def test_reorder_mismatch_is_conflict(client: TestClient) -> None:
    client.post(f"/api/days/{TODAY}/todos", json={"title": "A"})
    response = client.put(
        f"/api/days/{TODAY}/todos/order", json={"taskIds": ["missing"]}
    )
    assert response.status_code == 409
    assert response.json()["error"] == "Conflict"


def test_calendar_only_days_with_entries(client: TestClient) -> None:
    client.post(f"/api/days/{TODAY}/todos", json={"title": "有点"})
    empty_future = client.get(
        "/api/calendar", params={"from": "2026-08-01", "to": "2026-08-31"}
    )
    assert empty_future.status_code == 200
    body = empty_future.json()
    assert body["today"] == TODAY
    assert body["days"] == [{"date": TODAY, "todoCount": 1, "errandCount": 0}]
    tid = client.get(f"/api/days/{TODAY}").json()["todos"][0]["taskId"]
    client.post(f"/api/tasks/{tid}/unschedule")
    after = client.get(
        "/api/calendar", params={"from": "2026-08-01", "to": "2026-08-31"}
    )
    assert after.json()["days"] == []


def test_invalid_date_is_validation_error(client: TestClient) -> None:
    response = client.get("/api/days/2026-13-40")
    assert response.status_code == 400
    assert response.json()["error"] == "ValidationError"


def test_empty_title_is_validation_error(client: TestClient) -> None:
    response = client.post(f"/api/days/{TODAY}/todos", json={"title": "   "})
    assert response.status_code == 400
    assert response.json()["error"] == "ValidationError"


def test_meta_after_write(client: TestClient) -> None:
    client.post("/api/inventory/tasks", json={"title": "库存一件"})
    meta = client.get("/api/meta")
    assert meta.status_code == 200
    body = meta.json()
    assert body["today"] == TODAY
    assert body["timezone"] == "Asia/Shanghai"
    assert body["lastSettledDate"] == TODAY
    assert body["inventoryCount"] == 1


def test_debug_read(client: TestClient) -> None:
    debug = client.get("/api/debug")
    assert debug.status_code == 200
    body = debug.json()
    assert body["today"] == TODAY
    assert body["timezone"] == "Asia/Shanghai"
    assert body["lastSettledDate"] == TODAY
    assert body["schemaVersion"] == 1
    assert body["integrityCheck"] == "ok"
    assert "dbPath" in body
    assert set(body["counts"]) == {"tasks", "openDays", "sealedDays", "errands"}
