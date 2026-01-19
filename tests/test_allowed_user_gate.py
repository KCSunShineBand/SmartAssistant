import main
from fastapi.testclient import TestClient


def _update(chat_id=12345, user_id=99, text="/today"):
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "from": {"id": user_id},
            "chat": {"id": chat_id, "type": "private"},
            "text": text,
        },
    }


def test_webhook_allows_when_gate_not_configured(monkeypatch):
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_STRICT_OWNER_ONLY", raising=False)
    monkeypatch.setenv("APP_ENV", "dev")

    # prevent any real telegram call
    monkeypatch.setattr(main, "send_telegram_message", lambda chat_id, text: {"ok": True})

    client = TestClient(main.app)
    r = client.post("/telegram/webhook", json=_update(user_id=777))
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["type"] in {"message", "callback", "unsupported"}
    assert "sent" in data
    assert "actions" in data


def test_webhook_blocks_other_users_when_gate_set(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    monkeypatch.delenv("TELEGRAM_STRICT_OWNER_ONLY", raising=False)
    monkeypatch.setenv("APP_ENV", "dev")

    # If handle_event is called, that's a failure
    monkeypatch.setattr(main, "handle_event", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("handle_event should not be called for unauthorized users")
    ))

    client = TestClient(main.app)
    r = client.post("/telegram/webhook", json=_update(user_id=222))
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["unauthorized"] is True
    assert data["sent"] == 0
    assert data["actions"] == []


def test_webhook_processes_allowed_user(monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    monkeypatch.delenv("TELEGRAM_STRICT_OWNER_ONLY", raising=False)
    monkeypatch.setenv("APP_ENV", "dev")

    monkeypatch.setattr(
        main,
        "handle_event",
        lambda event, state: [{"type": "reply", "chat_id": 12345, "text": "pong"}],
    )

    sent = {"count": 0}

    def fake_send(chat_id: int, text: str):
        assert chat_id == 12345
        assert text == "pong"
        sent["count"] += 1
        return {"ok": True}

    monkeypatch.setattr(main, "send_telegram_message", fake_send)

    client = TestClient(main.app)
    r = client.post("/telegram/webhook", json=_update(user_id=111, text="/help"))
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["sent"] == 1
    assert sent["count"] == 1


def test_webhook_strict_mode_blocks_when_gate_missing(monkeypatch):
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_STRICT_OWNER_ONLY", "1")
    monkeypatch.setenv("APP_ENV", "dev")

    # If handle_event is called, that's a failure
    monkeypatch.setattr(main, "handle_event", lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("handle_event should not be called in strict mode without allow id")
    ))

    client = TestClient(main.app)
    r = client.post("/telegram/webhook", json=_update(user_id=999))
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["unauthorized"] is True
    assert data["actions"] == []
