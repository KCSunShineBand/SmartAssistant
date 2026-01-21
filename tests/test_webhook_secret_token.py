from fastapi.testclient import TestClient
import main


def _update(chat_id=7, user_id=9, text="/help"):
    return {
        "update_id": 1,
        "message": {"chat": {"id": chat_id}, "from": {"id": user_id}, "text": text},
    }


def test_webhook_rejects_when_secret_missing(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cr3t")

    called = {"n": 0}
    def fake_handle(event, state):
        called["n"] += 1
        return [{"type": "reply", "chat_id": 12345, "text": "pong"}]

    sent = {"n": 0}
    def fake_send(chat_id: int, text: str):
        sent["n"] += 1
        return {"ok": True}

    monkeypatch.setattr(main, "handle_event", fake_handle)
    monkeypatch.setattr(main, "send_telegram_message", fake_send)

    client = TestClient(main.app)
    r = client.post("/telegram/webhook", json=_update())

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body.get("unauthorized") is True
    assert body["sent"] == 0
    assert body["errors"] == 0
    assert called["n"] == 0
    assert sent["n"] == 0


def test_webhook_allows_when_secret_matches(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cr3t")

    monkeypatch.setattr(
        main,
        "handle_event",
        lambda event, state: [{"type": "reply", "chat_id": 12345, "text": "pong"}],
    )

    sent = {"n": 0}
    def fake_send(chat_id: int, text: str):
        assert chat_id == 12345
        assert text == "pong"
        sent["n"] += 1
        return {"ok": True}

    monkeypatch.setattr(main, "send_telegram_message", fake_send)

    client = TestClient(main.app)
    r = client.post(
        "/telegram/webhook",
        json=_update(),
        headers={"X-Telegram-Bot-Api-Secret-Token": "s3cr3t"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body.get("unauthorized") is None
    assert body["sent"] == 1
    assert body["errors"] == 0
    assert sent["n"] == 1
