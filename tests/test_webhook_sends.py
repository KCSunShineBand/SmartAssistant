from fastapi.testclient import TestClient
import main


def test_webhook_executes_send(monkeypatch):
    sent = {}

    def fake_send(chat_id: int, text: str):
        sent["chat_id"] = chat_id
        sent["text"] = text
        return {"ok": True}

    monkeypatch.setattr(main, "send_telegram_message", fake_send)

    client = TestClient(main.app)
    r = client.post(
        "/telegram/webhook",
        json={"update_id": 1, "message": {"chat": {"id": 7}, "from": {"id": 9}, "text": "/note hello"}},
    )

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["sent"] == 1
    assert body["errors"] == 0
    assert sent["chat_id"] == 7
    assert "Saved note" in sent["text"]
