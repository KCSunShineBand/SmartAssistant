from fastapi.testclient import TestClient

from main import app, normalize_update


def test_normalize_message_note_command():
    update = {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "from": {"id": 99, "username": "kc"},
            "chat": {"id": 12345, "type": "private"},
            "text": "/note buy milk",
        },
    }
    event = normalize_update(update)
    assert event["type"] == "message"
    assert event["chat_id"] == 12345
    assert event["user_id"] == 99
    assert event["route"]["kind"] == "command"
    assert event["route"]["command"] == "note"
    assert event["route"]["text"] == "buy milk"


def test_normalize_callback_parses_action_and_params():
    update = {
        "update_id": 2,
        "callback_query": {
            "id": "abc",
            "from": {"id": 99},
            "message": {"message_id": 11, "chat": {"id": 12345, "type": "private"}},
            "data": "LABEL_TOGGLE|id=abc123|label=LG+Admin",
        },
    }
    event = normalize_update(update)
    assert event["type"] == "callback"
    assert event["chat_id"] == 12345
    assert event["callback"]["action"] == "LABEL_TOGGLE"
    assert event["callback"]["params"]["id"] == "abc123"
    assert event["callback"]["params"]["label"] == "LG Admin"


def test_webhook_endpoint_returns_200_and_ack_type():
    client = TestClient(app)
    resp = client.post("/telegram/webhook", json={"update_id": 1, "message": {"chat": {"id": 1}, "text": "hi"}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["type"] in {"message", "callback", "unsupported"}
