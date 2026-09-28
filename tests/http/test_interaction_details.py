"""Interaction behavior through the real SQLite/HTTP path, including day rollover."""
from local_planner.persistence import SqliteUnitOfWork

TODAY = "2026-08-30"
NEXT = "2026-08-31"


def add(client, title="报告"):
    return client.post("/api/inventory/tasks", json={"title": title}).json()


def edit(client, item, notes, title=None, kind="tasks"):
    return client.patch(f"/api/{kind}/{item.get('taskId', item.get('id'))}/details", json={
        "title": title or item["title"], "notes": notes,
        "expectedTitle": item["title"], "expectedNotes": item["notes"],
    })


def test_notes_follow_scheduling_and_keep_historical_snapshot(client, clock, tmp_path):
    item = add(client)
    item = edit(client, item, "初稿\r\n材料", "研究报告").json()
    assert item["notes"] == "初稿\n材料"
    plan = client.post(f"/api/tasks/{item['taskId']}/schedule", json={"date": TODAY}).json()
    assert plan["todos"][0]["notes"] == item["notes"]
    clock.set(f"{NEXT}T08:00:00+08:00")
    inventory = client.get("/api/inventory").json()["items"][0]
    assert inventory["notes"] == item["notes"]
    edited = edit(client, inventory, "最终材料", "新报告")
    assert edited.status_code == 200
    past = client.get(f"/api/days/{TODAY}").json()
    assert past["writable"] is False
    assert (past["todos"][0]["title"], past["todos"][0]["notes"]) == ("研究报告", "初稿\n材料")
    scheduled = client.post(f"/api/tasks/{item['taskId']}/schedule", json={"date": NEXT}).json()
    assert scheduled["todos"][0]["notes"] == "最终材料"
    reopened = SqliteUnitOfWork.open(tmp_path / "planner.sqlite")
    try:
        assert reopened.get_task(item["taskId"]).notes == "最终材料"
        assert reopened.get_entry(TODAY, item["taskId"]).notes_snapshot == "初稿\n材料"
    finally:
        reopened.close()


def test_edit_is_atomic_and_stale_draft_cannot_overwrite_agent_change(client):
    item = add(client)
    assert edit(client, item, "旧备注").status_code == 200
    stale = edit(client, item, "本地草稿", "新标题")
    assert stale.status_code == 409
    current = client.get("/api/inventory").json()["items"][0]
    assert current["title"] == item["title"] and current["notes"] == "旧备注"
    assert edit(client, current, "a" * 10001, "错误标题").status_code == 400
    assert client.get("/api/inventory").json()["items"][0] == current
    assert edit(client, current, "").json()["notes"] == ""


def test_past_completed_task_and_expired_errand_reject_details_edit(client, clock):
    item = client.post(f"/api/days/{TODAY}/todos", json={"title": "完成"}).json()["todos"][0]
    client.post(f"/api/days/{TODAY}/todos/{item['taskId']}/complete")
    errand = client.post(f"/api/days/{TODAY}/errands", json={"title": "零碎"}).json()["errands"][0]
    assert edit(client, errand, "保留记录", kind="errands").status_code == 200
    clock.set(f"{NEXT}T00:00:00+08:00")
    assert edit(client, item, "不允许").status_code == 409
    errand["notes"] = "保留记录"
    assert edit(client, errand, "不允许", kind="errands").status_code == 409
    assert client.get(f"/api/days/{TODAY}").json()["errands"][0]["notes"] == "保留记录"


def test_search_matches_notes_casefold_and_excludes_completed_deleted_history(client, clock):
    item = edit(client, add(client, "写报告"), "Review 实验材料").json()
    assert client.get("/api/search", params={"q": "review 材料"}).json()["items"][0]["id"] == item["taskId"]
    other = add(client, "Review later")
    client.post(f"/api/tasks/{other['taskId']}/schedule", json={"date": NEXT})
    errand = client.post(f"/api/days/{TODAY}/errands", json={"title": "Review errand"}).json()["errands"][0]
    done = add(client, "Review done")
    client.post(f"/api/inventory/tasks/{done['taskId']}/complete")
    deleted = add(client, "Review deleted")
    client.delete(f"/api/tasks/{deleted['taskId']}")
    results = client.get("/api/search", params={"q": "review"}).json()
    assert {r["id"] for r in results["items"]} == {item["taskId"], other["taskId"], errand["id"]}
    assert {r["date"] for r in results["items"]} == {None, TODAY, NEXT}
    clock.set(f"{NEXT}T08:00:00+08:00")
    assert {r["id"] for r in client.get("/api/search", params={"q": "review"}).json()["items"]} == {item["taskId"], other["taskId"]}
    assert client.get("/api/search", params={"q": "   "}).json()["items"] == []
    assert client.get("/api/search", params={"q": "%_"}).json()["items"] == []


def test_manual_sort_overrides_times_and_survives_sealing_and_restore(client, clock):
    a = client.post(f"/api/days/{TODAY}/todos", json={"title": "晚些", "startClock": "15:00"}).json()["todos"][0]["taskId"]
    b = client.post(f"/api/days/{TODAY}/todos", json={"title": "较早", "startClock": "09:00"}).json()["todos"][0]["taskId"]
    assert a != b
    path = f"/api/days/{TODAY}"
    assert [i["taskId"] for i in client.get(path).json()["todos"]] == [b, a]
    ordered = client.put(path + "/todos/order", json={"taskIds": [a, b]}).json()
    assert ordered["manualTodoOrder"]
    assert [i["taskId"] for i in ordered["todos"]] == [a, b]
    automatic = client.put(path + "/todos/order", json={"taskIds": [a, b], "manual": False}).json()
    assert not automatic["manualTodoOrder"]
    assert [i["taskId"] for i in automatic["todos"]] == [b, a]
    client.put(path + "/todos/order", json={"taskIds": [a, b]})
    saved = client.post("/api/backups").json()
    clock.set(f"{NEXT}T08:00:00+08:00")
    past = client.get(path).json()
    assert past["manualTodoOrder"] and not past["writable"]
    assert [i["taskId"] for i in past["todos"]] == [a, b]
    assert client.put(path + "/todos/order", json={"taskIds": [b, a]}).status_code == 409
    assert client.post("/api/backups/restore", json={"name": saved["name"]}).status_code == 200
    assert [i["taskId"] for i in client.get(path).json()["todos"]] == [a, b]


def test_notes_survive_delete_undo_and_backup_restore(client):
    item = edit(client, add(client), "备份备注").json()
    saved = client.post("/api/backups").json()
    token = client.delete(f"/api/tasks/{item['taskId']}").json()["undo"]["token"]
    assert client.post(f"/api/undo/{token}").status_code == 200
    assert client.get("/api/inventory").json()["items"][0]["notes"] == "备份备注"
    edit(client, item, "修改")
    assert client.post("/api/backups/restore", json={"name": saved["name"]}).status_code == 200
    assert client.get("/api/inventory").json()["items"][0]["notes"] == "备份备注"


def test_quick_entry_uses_server_day_after_midnight(client, clock):
    assert client.post("/api/quick-entry", json={"title": "待办"}).json()["notes"] == ""
    clock.set(f"{NEXT}T00:00:01+08:00")
    today = client.post("/api/quick-entry", json={"title": "今天", "destination": "today"})
    assert today.status_code == 200
    assert today.json()["date"] == NEXT
    assert today.json()["todos"][0]["title"] == "今天"
    assert client.post("/api/quick-entry", json={"title": " "}).status_code == 400
    assert client.post("/api/quick-entry", json={"title": "test", "destination": "other"}).status_code == 400
