from fastapi.testclient import TestClient

from main import app


def test_webhook_message_returns_actions():
    client = TestClient(app)
    r = client.post(
        "/telegram/webhook",
        json={"update_id": 1, "message": {"chat": {"id": 1}, "from": {"id": 9}, "text": "/todo buy milk"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["type"] == "message"
    assert isinstance(body["actions"], list)
    assert body["actions"][0]["type"] == "reply"
    assert body["actions"][0]["chat_id"] == 1
