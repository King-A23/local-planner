import base64
import sqlite3
from contextlib import closing

from local_planner.runtime import interprocess_lock
from local_planner.persistence import SqliteUnitOfWork
from local_planner.recovery import ensure_daily_backup


def add(client, title="保留事项"):
    return client.post("/api/inventory/tasks", json={"title": title}).json()["taskId"]


def titles(client):
    return {item["title"] for item in client.get("/api/inventory").json()["items"]}


def test_restore_and_safety_backup_preserve_live_connections(client, tmp_path):
    add(client)
    saved = client.post("/api/backups").json()
    add(client, "之后添加")
    other = SqliteUnitOfWork.open(tmp_path / "planner.sqlite")
    try:
        response = client.post("/api/backups/restore", json={"name": saved["name"]})
        assert response.status_code == 200, response.text
        assert titles(client) == {"保留事项"}
        assert {t.title for t in other.list_inventory_tasks()} == {"保留事项"}
        safety = response.json()["safetyBackup"]
        assert client.post("/api/backups/restore", json={"name": safety["name"]}).status_code == 200
        assert titles(client) == {"保留事项", "之后添加"}
    finally:
        other.close()


def test_download_import_and_restore(client):
    add(client)
    saved = client.post("/api/backups").json()
    downloaded = client.get(f"/api/backups/{saved['name']}/download")
    assert downloaded.content.startswith(b"SQLite format 3")
    assert "attachment" in downloaded.headers["content-disposition"]
    imported = client.post("/api/backups/import", json={"content": base64.b64encode(downloaded.content).decode()})
    assert imported.status_code == 200, imported.text
    add(client, "later")
    assert client.post("/api/backups/restore", json={"name": imported.json()["name"]}).status_code == 200
    assert titles(client) == {"保留事项"}


def test_invalid_files_and_traversal_cannot_replace_data(client, tmp_path):
    add(client)
    assert client.post("/api/backups/import", json={"content": "not base64"}).status_code == 400
    assert client.post("/api/backups/import", json={"content": base64.b64encode(b"not sqlite").decode()}).status_code == 400
    other = tmp_path / "other.sqlite"
    with closing(sqlite3.connect(other)) as conn:
        conn.execute("CREATE TABLE example(value TEXT)")
        conn.commit()
    assert client.post("/api/backups/import", json={"content": base64.b64encode(other.read_bytes()).decode()}).status_code == 400
    assert client.post("/api/backups/restore", json={"name": "../planner.sqlite"}).status_code == 404
    assert titles(client) == {"保留事项"}


def test_future_or_modified_schema_is_rejected(client, tmp_path):
    add(client)
    backup = client.post("/api/backups").json()
    path = tmp_path / "backups" / backup["name"]
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("INSERT INTO schema_migrations VALUES (999,'future')")
        conn.commit()
    assert client.post("/api/backups/restore", json={"name": backup["name"]}).status_code == 400
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("DELETE FROM schema_migrations WHERE version=999")
        conn.execute("CREATE TRIGGER unexpected AFTER INSERT ON tasks BEGIN DELETE FROM errands; END")
        conn.commit()
    assert client.post("/api/backups/restore", json={"name": backup["name"]}).status_code == 400
    assert titles(client) == {"保留事项"}


def test_running_or_paused_agent_lease_blocks_restore(client, tmp_path):
    add(client)
    backup = client.post("/api/backups").json()
    with interprocess_lock(tmp_path / "agent-execution", timeout=0):
        response = client.post("/api/backups/restore", json={"name": backup["name"]})
    assert response.status_code == 409
    assert "助手" in response.json()["message"]
    assert titles(client) == {"保留事项"}


def test_daily_backups_retention_never_prunes_manual(client, uow, tmp_path):
    add(client)
    manual = client.post("/api/backups").json()
    for day in range(1, 22):
        ensure_daily_backup(uow.conn, tmp_path, f"2026-09-{day:02}")
    daily = list((tmp_path / "backups").glob("auto-*.sqlite"))
    assert len(daily) == 14
    assert (tmp_path / "backups" / manual["name"]).exists()
    latest = tmp_path / "backups/auto-2026-09-21.sqlite"
    original = latest.read_bytes()
    add(client, "not in daily snapshot")
    ensure_daily_backup(uow.conn, tmp_path, "2026-09-21")
    assert latest.read_bytes() == original


def test_undo_restores_single_deletion_without_losing_later_writes(client):
    task = add(client, "被删事项")
    token = client.delete(f"/api/tasks/{task}").json()["undo"]["token"]
    add(client, "新事项")
    assert client.post(f"/api/undo/{token}").status_code == 200
    assert titles(client) == {"被删事项", "新事项"}
    assert client.post(f"/api/undo/{token}").status_code == 409


def test_undo_errand_collision_and_midnight_readonly(client, clock):
    day = "2026-08-30"
    first = client.post(f"/api/days/{day}/errands", json={"title": "A", "startClock": "09:00"}).json()["errands"][0]
    token = client.delete(f"/api/errands/{first['id']}").json()["undo"]["token"]
    client.post(f"/api/days/{day}/errands", json={"title": "B"})
    assert client.post(f"/api/undo/{token}").status_code == 200
    items = client.get(f"/api/days/{day}").json()["errands"]
    assert {item["title"] for item in items} == {"A", "B"}
    assert next(e for e in items if e["title"] == "A")["startClock"] == "09:00"
    token = client.delete(f"/api/errands/{first['id']}").json()["undo"]["token"]
    clock.set("2026-08-31T12:00:00+08:00")
    assert client.post(f"/api/undo/{token}").status_code == 409
    assert len(client.get(f"/api/days/{day}").json()["errands"]) == 1


def test_restore_invalidates_pre_restore_undo(client):
    task = add(client)
    token = client.delete(f"/api/tasks/{task}").json()["undo"]["token"]
    backup = client.post("/api/backups").json()
    assert client.post("/api/backups/restore", json={"name": backup["name"]}).status_code == 200
    assert client.post(f"/api/undo/{token}").status_code == 409
    assert titles(client) == set()


def test_undo_inventory_with_history_preserves_history(client, clock):
    plan = client.post("/api/days/2026-08-30/todos", json={"title": "历史计划"}).json()
    task = plan["todos"][0]["taskId"]
    clock.set("2026-08-31T12:00:00+08:00")
    before = client.get("/api/days/2026-08-30").json()
    token = client.delete(f"/api/tasks/{task}").json()["undo"]["token"]
    assert client.post(f"/api/undo/{token}").status_code == 200
    assert client.get("/api/days/2026-08-30").json() == before
    assert titles(client) == {"历史计划"}


def test_restore_backup_failure_does_not_replace_current_data(client, monkeypatch):
    from local_planner import recovery
    add(client, 'before')
    saved = client.post('/api/backups').json()
    add(client, 'must survive')
    def fail(*args, **kwargs):
        raise OSError('disk full')
    monkeypatch.setattr(recovery, 'snapshot', fail)
    response = client.post('/api/backups/restore', json={'name': saved['name']})
    assert response.status_code == 500
    assert titles(client) == {'before', 'must survive'}


def test_undo_recurring_occurrence_and_stopped_series(client):
    series = client.post('/api/recurrences', json={
        'title': '散步', 'kind': 'plan', 'frequency': 'daily', 'startDate': '2026-08-30',
    }).json()
    day = client.get('/api/days/2026-08-30').json()
    task = day['todos'][0]['taskId']
    token = client.delete(f'/api/tasks/{task}').json()['undo']['token']
    assert client.post(f'/api/undo/{token}').status_code == 200
    item = client.get('/api/days/2026-08-30').json()['todos'][0]
    assert item['recurrence']['seriesId'] == series['id']
    client.post(f"/api/recurrences/{series['id']}/stop")
    token = client.delete(f"/api/recurrences/{series['id']}").json()['undo']['token']
    assert client.post(f'/api/undo/{token}').status_code == 200
    assert client.get('/api/recurrences').json()['items'][0]['state'] == 'stopped'


def test_undo_scheduled_task_after_sort_collision(client):
    endpoint = '/api/days/2026-08-30/todos'
    first = client.post(endpoint, json={'title': 'first', 'startClock': '10:00'}).json()['todos'][0]
    token = client.delete(f"/api/tasks/{first['taskId']}").json()['undo']['token']
    client.post(endpoint, json={'title': 'second'})
    assert client.post(f'/api/undo/{token}').status_code == 200
    items = client.get('/api/days/2026-08-30').json()['todos']
    assert {t['title'] for t in items} == {'first', 'second'}
    assert next(t for t in items if t['title'] == 'first')['startClock'] == '10:00'


def test_older_backup_migrates_in_staging_and_corrupt_symlink_rejected(client, tmp_path):
    from local_planner.persistence.connection import MIGRATIONS_DIR, sql_statements
    source = tmp_path / 'backups' / 'old.sqlite'
    source.parent.mkdir(exist_ok=True)
    with closing(sqlite3.connect(source)) as conn:
        for statement in sql_statements((MIGRATIONS_DIR / '001_init.sql').read_text()):
            conn.execute(statement)
        conn.execute("INSERT INTO schema_migrations VALUES (1, '2026-01-01T00:00:00Z')")
        conn.execute("INSERT INTO meta VALUES ('timezone','Asia/Shanghai')")
        conn.commit()
    add(client, 'current')
    response = client.post('/api/backups/restore', json={'name': 'old.sqlite'})
    assert response.status_code == 200, response.text
    assert titles(client) == set()
    add(client, 'after migration')
    assert titles(client) == {'after migration'}
    (source.parent / 'linked.sqlite').symlink_to(tmp_path / 'planner.sqlite')
    assert client.get('/api/backups/linked.sqlite/download').status_code == 404
    assert client.post('/api/backups/restore', json={'name': 'linked.sqlite'}).status_code == 404
