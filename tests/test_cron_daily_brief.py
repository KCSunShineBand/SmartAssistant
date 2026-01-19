from fastapi.testclient import TestClient
import main


def _force_local_mode(monkeypatch):
    # Prevent any accidental Notion/DB usage inside handle_event during this test.
    for k in ["NOTION_TOKEN", "NOTION_NOTES_DB_ID", "NOTION_TASKS_DB_ID", "DATABASE_URL"]:
        monkeypatch.delenv(k, raising=False)


def test_cron_daily_brief_requires_chat_id_or_env(monkeypatch):
    _force_local_mode(monkeypatch)

    client = TestClient(main.app)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("CRON_DAILY_BRIEF_KEY", raising=False)

    r = client.post("/cron/daily-brief", json={})
    assert r.status_code == 400
    assert "chat_id missing" in r.json()["detail"]


def test_cron_daily_brief_ok_with_env_chat_id(monkeypatch):
    _force_local_mode(monkeypatch)

    client = TestClient(main.app)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.delenv("CRON_DAILY_BRIEF_KEY", raising=False)

    r = client.post("/cron/daily-brief", json={})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert isinstance(data["actions"], list)
    assert "Daily Brief (" in data["actions"][0]["text"]



def test_cron_daily_brief_key_enforced(monkeypatch):
    _force_local_mode(monkeypatch)

    client = TestClient(main.app)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("CRON_DAILY_BRIEF_KEY", "sekrit")

    r = client.post("/cron/daily-brief", json={})
    assert r.status_code == 401

    r2 = client.post("/cron/daily-brief", json={}, headers={"X-Cron-Key": "sekrit"})
    assert r2.status_code == 200
    assert r2.json()["ok"] is True

def test_cron_daily_brief_accepts_octet_stream_body(monkeypatch):
    _force_local_mode(monkeypatch)

    client = TestClient(main.app)
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
    monkeypatch.delenv("CRON_DAILY_BRIEF_KEY", raising=False)

    r = client.post(
        "/cron/daily-brief",
        content=b"{}",
        headers={"Content-Type": "application/octet-stream"},
    )

    assert r.status_code == 200
    assert r.json()["ok"] is True
