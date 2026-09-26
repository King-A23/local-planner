"""Optional To Do target date and Plan/Errands clocks through HTTP."""

from __future__ import annotations

from fastapi.testclient import TestClient

TODAY = "2026-08-30"
YESTERDAY = "2026-08-29"


def test_inventory_target_date_stays_unscheduled(client: TestClient) -> None:
    created = client.post(
        "/api/inventory/tasks",
        json={"title": "目标日任务", "targetDate": "2026-09-03"},
    )
    assert created.status_code == 200
    assert created.json()["targetDate"] == "2026-09-03"
    listed = client.get("/api/inventory").json()["items"]
    assert listed[0]["targetDate"] == "2026-09-03"
    today = client.get(f"/api/days/{TODAY}").json()
    assert today["todos"] == []
    patched = client.patch(
        f"/api/tasks/{created.json()['taskId']}/target",
        json={"date": None},
    )
    assert patched.status_code == 200
    assert patched.json()["targetDate"] is None


def test_plan_and_errand_clocks_via_http(client: TestClient) -> None:
    start_only = client.post(
        f"/api/days/{TODAY}/todos",
        json={"title": "只开始", "startClock": "09:00"},
    )
    assert start_only.status_code == 200
    todo = start_only.json()["todos"][0]
    assert todo["startClock"] == "09:00"
    assert todo["endClock"] is None
    tid = todo["taskId"]
    both = client.patch(
        f"/api/days/{TODAY}/todos/{tid}/clocks",
        json={"startClock": "09:00", "endClock": "11:00"},
    )
    assert both.json()["todos"][0]["endClock"] == "11:00"
    bad = client.patch(
        f"/api/days/{TODAY}/todos/{tid}/clocks",
        json={"startClock": "11:00", "endClock": "09:00"},
    )
    assert bad.status_code == 400
    errand = client.post(
        f"/api/days/{TODAY}/errands",
        json={"title": "差事钟", "endClock": "17:00"},
    )
    eid = errand.json()["errands"][0]["id"]
    assert errand.json()["errands"][0]["startClock"] is None
    assert errand.json()["errands"][0]["endClock"] == "17:00"
    updated = client.patch(
        f"/api/errands/{eid}/clocks",
        json={"startClock": "13:00", "endClock": "17:00"},
    )
    assert updated.json()["errands"][0]["startClock"] == "13:00"
    past = client.patch(
        f"/api/days/{YESTERDAY}/todos/nope/clocks",
        json={"startClock": "09:00"},
    )
    assert past.status_code == 409


def test_timed_items_sort_before_untimed_earlier_start_first(
    client: TestClient,
) -> None:
    client.post(f"/api/days/{TODAY}/todos", json={"title": "无时间"})
    client.post(
        f"/api/days/{TODAY}/todos",
        json={"title": "十一点", "startClock": "11:00"},
    )
    client.post(
        f"/api/days/{TODAY}/todos",
        json={"title": "九点", "startClock": "09:00"},
    )
    client.post(
        f"/api/days/{TODAY}/todos",
        json={"title": "只结束", "endClock": "08:00"},
    )
    titles = [item["title"] for item in client.get(f"/api/days/{TODAY}").json()["todos"]]
    assert titles == ["只结束", "九点", "十一点", "无时间"]
    client.post(f"/api/days/{TODAY}/errands", json={"title": "差事无钟"})
    client.post(
        f"/api/days/{TODAY}/errands",
        json={"title": "差事晚", "startClock": "16:00"},
    )
    client.post(
        f"/api/days/{TODAY}/errands",
        json={"title": "差事早", "startClock": "10:00"},
    )
    errands = [
        item["title"]
        for item in client.get(f"/api/days/{TODAY}").json()["errands"]
    ]
    assert errands == ["差事早", "差事晚", "差事无钟"]
