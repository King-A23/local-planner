from fastapi.testclient import TestClient


def test_recurrence_crud_materializes_and_exposes_source(client: TestClient) -> None:
    created = client.post(
        "/api/recurrences",
        json={
            "kind": "plan",
            "title": "每周五周报",
            "frequency": "weekly",
            "weekdays": ["fri"],
            "startDate": "2026-08-30",
            "defaultEndClock": "18:00",
        },
    )
    assert created.status_code == 200
    series = created.json()
    assert series["state"] == "active"
    assert series["nextOccurrenceDate"] == "2026-09-04"
    friday = client.get("/api/days/2026-09-04").json()
    assert len(friday["todos"]) == 1
    assert friday["todos"][0]["seriesId"] == series["id"]
    assert friday["todos"][0]["occurrenceDate"] == "2026-09-04"
    assert friday["todos"][0]["recurrence"]["seriesId"] == series["id"]
    assert friday["todos"][0]["endClock"] == "18:00"
    assert client.post(f"/api/recurrences/{series['id']}/pause").json()["state"] == "paused"
    assert client.post(f"/api/recurrences/{series['id']}/resume").json()["state"] == "active"
    assert client.post(f"/api/recurrences/{series['id']}/stop").json()["state"] == "stopped"


def test_only_stopped_recurrence_can_be_deleted_without_losing_history(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/recurrences",
        json={
            "kind": "errand",
            "title": "吃药",
            "frequency": "daily",
            "startDate": "2026-08-30",
        },
    ).json()
    series_id = created["id"]
    assert client.delete(f"/api/recurrences/{series_id}").status_code == 409
    assert client.post(f"/api/recurrences/{series_id}/pause").status_code == 200
    assert client.delete(f"/api/recurrences/{series_id}").status_code == 409
    assert client.post(f"/api/recurrences/{series_id}/stop").status_code == 200

    deleted = client.delete(f"/api/recurrences/{series_id}")
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True
    assert deleted.json()["undo"]["token"]
    assert client.get("/api/recurrences").json() == {"items": []}
    today = client.get("/api/days/2026-08-30").json()
    assert today["errands"][0]["recurrence"]["seriesId"] == series_id
    assert client.delete(f"/api/recurrences/{series_id}").status_code == 404


def test_recurrence_cannot_start_in_the_past(client: TestClient) -> None:
    response = client.post(
        "/api/recurrences",
        json={
            "kind": "errand",
            "title": "过去的提醒",
            "frequency": "daily",
            "startDate": "2026-08-29",
        },
    )
    assert response.status_code == 400
    assert response.json()["error"] == "ValidationError"


def test_planning_today_is_explicit_and_idempotent(client: TestClient) -> None:
    before = client.get("/api/planning/today")
    assert before.status_code == 200
    assert before.json()["status"] == "unplanned"
    done = client.post("/api/planning/today/complete")
    assert done.status_code == 200
    assert done.json()["status"] == "ready"
    assert (
        client.post("/api/planning/today/complete").json()["plannedAt"]
        == done.json()["plannedAt"]
    )
    assert client.get("/api/meta").json()["planningStatus"] == "ready"
