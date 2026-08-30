"""Sealed/past writes are 409 DaySealed, never 500. Expired uncomplete is Conflict."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from local_planner.clock import FrozenClock
from local_planner.domain.commands import Planner
from local_planner.http.app import create_app
from local_planner.persistence import SqliteUnitOfWork

TODAY = "2026-08-30"
YESTERDAY = "2026-08-29"
FROZEN = "2026-08-30T12:00:00+08:00"


def _client(app) -> TestClient:
    return TestClient(app, base_url="http://127.0.0.1:8787")


def test_past_day_writes_are_day_sealed(client: TestClient) -> None:
    add_todo = client.post(f"/api/days/{YESTERDAY}/todos", json={"title": "补昨天"})
    assert add_todo.status_code == 409
    assert add_todo.json()["error"] == "DaySealed"
    add_errand = client.post(f"/api/days/{YESTERDAY}/errands", json={"title": "补差事"})
    assert add_errand.status_code == 409
    assert add_errand.json()["error"] == "DaySealed"
    opened = client.get(f"/api/days/{YESTERDAY}")
    assert opened.status_code == 200
    assert opened.json()["writable"] is False
    assert opened.json()["isPast"] is True
    assert opened.json()["status"] == "sealed"


def test_sealed_errand_complete_is_409_not_500(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    clock = FrozenClock(FROZEN)
    uow = SqliteUnitOfWork.open(tmp_path / "planner.sqlite")
    try:
        planner = Planner(clock=clock, uow=uow)
        with uow.transaction():
            plan = planner.add_errand(TODAY, "封印差事")
            eid = plan.errands[0].id
            planner.seal_day(TODAY)
        with _client(create_app(clock=clock, uow=uow, port=8787, dev=False)) as client:
            with caplog.at_level(logging.INFO, logger="local_planner.http.app"):
                complete = client.post(f"/api/errands/{eid}/complete")
            assert complete.status_code == 409
            assert complete.status_code != 500
            assert complete.json()["error"] == "DaySealed"
            assert any(
                rec.getMessage().startswith("reject code=DaySealed")
                and f"date={TODAY}" in rec.getMessage()
                for rec in caplog.records
            )
            rename = client.patch(f"/api/errands/{eid}", json={"title": "篡改"})
            assert rename.status_code == 409
            assert rename.json()["error"] == "DaySealed"
            delete = client.delete(f"/api/errands/{eid}")
            assert delete.status_code == 409
            assert delete.json()["error"] == "DaySealed"
            day = client.get(f"/api/days/{TODAY}").json()
            assert day["errands"][0]["title"] == "封印差事"
            assert day["errands"][0]["status"] == "expired"
    finally:
        uow.close()


def test_expired_errand_uncomplete_is_conflict(tmp_path: Path) -> None:
    clock = FrozenClock("2026-08-29T12:00:00+08:00")
    uow = SqliteUnitOfWork.open(tmp_path / "planner.sqlite")
    try:
        planner = Planner(clock=clock, uow=uow)
        with uow.transaction():
            plan = planner.add_errand(YESTERDAY, "将作废")
            eid = plan.errands[0].id
        clock.set(FROZEN)
        with _client(create_app(clock=clock, uow=uow, port=8787, dev=False)) as client:
            client.get("/api/meta")
            assert uow.get_errand(eid).status == "expired"
            uncomplete = client.post(f"/api/errands/{eid}/uncomplete")
            assert uncomplete.status_code == 409
            assert uncomplete.status_code != 500
            assert uncomplete.json()["error"] == "Conflict"
            complete = client.post(f"/api/errands/{eid}/complete")
            assert complete.status_code == 409
            assert complete.json()["error"] == "DaySealed"
    finally:
        uow.close()


def test_unknown_errand_is_not_found(client: TestClient) -> None:
    response = client.post("/api/errands/00000000-0000-4000-8000-000000000000/complete")
    assert response.status_code == 404
    assert response.json()["error"] == "NotFound"


def test_year_cap_on_write(client: TestClient) -> None:
    response = client.post("/api/days/2000-01-01/todos", json={"title": "太远"})
    assert response.status_code == 400
    assert response.json()["error"] == "ValidationError"
