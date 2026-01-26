import os
from fastapi.testclient import TestClient
import main


def test_edit_action_updates_description_and_rerenders(monkeypatch):
    # Ensure no auth gating blocks the test
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_STRICT_OWNER_ONLY", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_ID", raising=False)

    client = TestClient(main.app)

    chat_id = 123
    list_mid = 777

    # Seed render cache as if /today created a list message earlier
    main.STATE.render_cache[(chat_id, list_mid)] = {
        "list_kind": "today",
        "tasks": [
            {"id": "t1", "title": "Pay bills", "description": "Old desc", "due": None, "status": "todo"},
        ],
        "text": "Open tasks: 1\n1. Pay bills | Old desc",
    }

    # Force the webhook to process an edit action without relying on core routing
    def fake_handle_event(event, state):
        return [
            {
                "type": "edit",
                "chat_id": chat_id,
                "message_id": list_mid,
                "update_task": {"id": "t1", "description": "New desc"},
            }
        ]

    monkeypatch.setattr(main, "handle_event", fake_handle_event)

    captured = {}

    def fake_edit_telegram_message(chat_id, message_id, text, reply_markup=None, disable_web_page_preview=True):
        captured["chat_id"] = chat_id
        captured["message_id"] = message_id
        captured["text"] = text
        captured["reply_markup"] = reply_markup
        return {"ok": True}

    monkeypatch.setattr(main, "edit_telegram_message", fake_edit_telegram_message)

    # Any message update is fine; our fake_handle_event drives the action
    resp = client.post(
        "/telegram/webhook",
        json={
            "update_id": 1,
            "message": {
                "message_id": 1,
                "from": {"id": 999},
                "chat": {"id": chat_id},
                "text": "hi",
            },
        },
    )

    assert resp.status_code == 200
    assert captured["message_id"] == list_mid
    assert "New desc" in captured["text"]
    assert " | " in captured["text"]
