from fastapi.testclient import TestClient
import main


def test_webhook_rejects_when_secret_missing(monkeypatch):
    # Arrange
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "sekrit")

    called = {"handle_event": 0}

    def fake_handle_event(event, state):
        called["handle_event"] += 1
        return [{"type": "send_message", "chat_id": 123, "text": "should_not_send"}]

    # If actions somehow run, don't actually call Telegram API
    def fake_send_message(chat_id: int, text: str):
        raise AssertionError("send_telegram_message should not be called for unauthorized requests")

    monkeypatch.setattr(main, "handle_event", fake_handle_event)
    monkeypatch.setattr(main, "send_telegram_message", fake_send_message)

    client = TestClient(main.app)

    update = {
        "update_id": 1,
        "message": {"message_id": 1, "chat": {"id": 123}, "from": {"id": 7}, "text": "hi"},
    }

    # Act (no header)
    r = client.post("/telegram/webhook", json=update)

    # Assert
    assert r.status_code == 200
    body = r.json()
    assert body.get("unauthorized") is True
    assert body.get("actions") == []
    assert called["handle_event"] == 0


def test_webhook_rejects_when_secret_wrong(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "sekrit")

    called = {"handle_event": 0}

    def fake_handle_event(event, state):
        called["handle_event"] += 1
        return []

    monkeypatch.setattr(main, "handle_event", fake_handle_event)

    client = TestClient(main.app)

    update = {
        "update_id": 2,
        "message": {"message_id": 2, "chat": {"id": 123}, "from": {"id": 7}, "text": "hi"},
    }

    r = client.post(
        "/telegram/webhook",
        json=update,
        headers={"X-Telegram-Bot-Api-Secret-Token": "nope"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body.get("unauthorized") is True
    assert body.get("actions") == []
    assert called["handle_event"] == 0


def test_webhook_allows_when_secret_correct(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "sekrit")

    called = {"handle_event": 0, "sent": 0}

    def fake_handle_event(event, state):
        called["handle_event"] += 1
        # IMPORTANT: main.telegram_webhook only sends actions with type == "reply"
        return [{"type": "reply", "chat_id": 123, "text": "ok"}]

    def fake_send_message(chat_id: int, text: str):
        assert chat_id == 123
        assert text == "ok"
        called["sent"] += 1
        return {"ok": True}

    monkeypatch.setattr(main, "handle_event", fake_handle_event)
    monkeypatch.setattr(main, "send_telegram_message", fake_send_message)

    client = TestClient(main.app)

    update = {
        "update_id": 3,
        "message": {"message_id": 3, "chat": {"id": 123}, "from": {"id": 7}, "text": "hi"},
    }

    r = client.post(
        "/telegram/webhook",
        json=update,
        headers={"X-Telegram-Bot-Api-Secret-Token": "sekrit"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body.get("unauthorized") is not True
    assert called["handle_event"] == 1
    assert called["sent"] == 1
    assert body.get("sent") == 1

