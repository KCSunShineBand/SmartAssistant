import os
from fastapi.testclient import TestClient
import main


def test_admin_notion_setup_happy_path(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://ignored-for-test")
    monkeypatch.delenv("ADMIN_SETUP_KEY", raising=False)

    calls = {"settings": [], "labels": []}

    monkeypatch.setattr(main.db, "init_db", lambda: None)
    monkeypatch.setattr(main.db, "set_setting", lambda k, v: calls["settings"].append((k, v)))
    monkeypatch.setattr(main.db, "get_setting", lambda k, default=None: default)
    monkeypatch.setattr(main.db, "upsert_label", lambda name: calls["labels"].append(name))

    monkeypatch.setattr(
        main.notion,
        "setup_databases",
        lambda parent_page_id: {"notes_db_id": "NOTES123", "tasks_db_id": "TASKS123"},
    )

    client = TestClient(main.app)
    r = client.post("/admin/notion/setup", json={"parent_page_id": "PARENT123"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["notes_db_id"] == "NOTES123"
    assert body["tasks_db_id"] == "TASKS123"
    assert body["seeded_labels"] == 9

    # verify settings written
    assert ("notion_notes_db_id", "NOTES123") in calls["settings"]
    assert ("notion_tasks_db_id", "TASKS123") in calls["settings"]


def test_admin_notion_setup_requires_parent_page_id():
    client = TestClient(main.app)
    r = client.post("/admin/notion/setup", json={})
    assert r.status_code == 400


def test_admin_notion_setup_requires_admin_key_when_configured(monkeypatch):
    monkeypatch.setenv("ADMIN_SETUP_KEY", "secret")
    monkeypatch.setattr(main.db, "init_db", lambda: None)
    monkeypatch.setattr(main.notion, "setup_databases", lambda _: {"notes_db_id": "N", "tasks_db_id": "T"})
    monkeypatch.setattr(main.db, "set_setting", lambda *_: None)
    monkeypatch.setattr(main.db, "get_setting", lambda _k, default=None: default)
    monkeypatch.setattr(main.db, "upsert_label", lambda _name: None)

    client = TestClient(main.app)

    r = client.post("/admin/notion/setup", json={"parent_page_id": "P"})
    assert r.status_code == 401

    r2 = client.post(
        "/admin/notion/setup",
        json={"parent_page_id": "P"},
        headers={"X-Admin-Key": "secret"},
    )
    assert r2.status_code == 200
