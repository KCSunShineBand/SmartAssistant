from fastapi.testclient import TestClient
import main


def test_webhook_passes_reply_markup_to_send_message(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "sekrit")

    called = {"sent": 0}

    def fake_handle_event(event, state):
        return [
            {
                "type": "reply",
                "chat_id": 123,
                "text": "ok",
                "reply_markup": {
                    "inline_keyboard": [
                        [{"text": "Open", "url": "https://example.com"}],
                        [{"text": "Do", "callback_data": "do|x=1"}],
                    ]
                },
            }
        ]

    def fake_send_message(chat_id: int, text: str, **kwargs):
        assert chat_id == 123
        assert text == "ok"
        assert "reply_markup" in kwargs
        rm = kwargs["reply_markup"]
        assert isinstance(rm, dict)
        assert "inline_keyboard" in rm
        called["sent"] += 1
        return {"ok": True}

    monkeypatch.setattr(main, "handle_event", fake_handle_event)
    monkeypatch.setattr(main, "send_telegram_message", fake_send_message)

    client = TestClient(main.app)

    update = {
        "update_id": 99,
        "message": {"message_id": 1, "chat": {"id": 123}, "from": {"id": 7}, "text": "hi"},
    }

    r = client.post(
        "/telegram/webhook",
        json=update,
        headers={"X-Telegram-Bot-Api-Secret-Token": "sekrit"},
    )

    assert r.status_code == 200
    body = r.json()
    assert body.get("sent") == 1
    assert called["sent"] == 1
