import main
import requests
from fastapi.testclient import TestClient


class _Resp:
    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True}


def test_webhook_answers_callback_query(monkeypatch):
    # Avoid token checks by bypassing _tg_api_url
    monkeypatch.setattr(main, "_tg_api_url", lambda method: f"https://example.com/{method}")

    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append((url, json))
        return _Resp()

    monkeypatch.setattr(requests, "post", fake_post)

    # Don't send any messages (we're testing callback ack only)
    monkeypatch.setattr(main, "handle_event", lambda event, state: [])

    client = TestClient(main.app)

    update = {
        "update_id": 1,
        "callback_query": {
            "id": "cbq_123",
            "from": {"id": 9},
            "data": "today",
            "message": {"message_id": 77, "chat": {"id": 555}},
        },
    }

    r = client.post("/telegram/webhook", json=update)
    assert r.status_code == 200

    # Verify answerCallbackQuery called
    assert any(
        u.endswith("/answerCallbackQuery") and payload.get("callback_query_id") == "cbq_123"
        for (u, payload) in calls
    )
