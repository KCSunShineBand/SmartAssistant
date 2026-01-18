from fastapi.testclient import TestClient
import main


def test_webhook_skips_send_when_token_missing(monkeypatch):
    # Make send_telegram_message raise RuntimeError like missing token would
    def fake_send(chat_id: int, text: str):
        raise RuntimeError("Telegram token not configured")

    monkeypatch.setattr(main, "send_telegram_message", fake_send)

    client = TestClient(main.app)
    r = client.post(
        "/telegram/webhook",
        json={"update_id": 1, "message": {"chat": {"id": 7}, "from": {"id": 9}, "text": "/note hello"}},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["sent"] == 0
    assert body["errors"] == 0
