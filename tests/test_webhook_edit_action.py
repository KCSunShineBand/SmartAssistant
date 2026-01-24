import main
from fastapi.testclient import TestClient


def test_webhook_executes_edit_action(monkeypatch):
    monkeypatch.setattr(main, "handle_event", lambda event, state: [
        {"type": "edit", "chat_id": 555, "message_id": 77, "remove_task_id": "page_1"}
    ])

    called = {"n": 0}

    def fake_edit(chat_id: int, message_id: int, text: str, **kwargs):
        assert chat_id == 555
        assert message_id == 77
        assert "page_1" in text
        called["n"] += 1
        return {"ok": True}

    monkeypatch.setattr(main, "edit_telegram_message", fake_edit)

    client = TestClient(main.app)
    update = {
        "update_id": 1,
        "callback_query": {
            "id": "cbq_123",
            "from": {"id": 9},
            "data": "done|task_id=page_1",
            "message": {"message_id": 77, "chat": {"id": 555}},
        },
    }

    r = client.post("/telegram/webhook", json=update)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert called["n"] == 1
