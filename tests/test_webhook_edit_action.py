import main
from fastapi.testclient import TestClient


def test_webhook_executes_edit_action(monkeypatch):
    # Core returns an edit action; webhook should execute edit_telegram_message.
    monkeypatch.setattr(
        main,
        "handle_event",
        lambda event, state: [
            {"type": "edit", "chat_id": 555, "message_id": 77, "remove_task_id": "page_1"}
        ],
    )

    # Seed cache so webhook can rerender something meaningful
    main.STATE.render_cache[(555, 77)] = {
        "list_kind": "today",
        "tasks": [
            {"id": "page_1", "title": "Pay rent", "due": None, "status": "todo"},
            {"id": "page_2", "title": "Write report", "due": None, "status": "doing"},
        ],
        "text": "Open tasks: 2 ...",
    }

    called = {"n": 0}

    def fake_edit(chat_id: int, message_id: int, text: str, **kwargs):
        assert chat_id == 555
        assert message_id == 77
        # New UX: should NOT leak Notion ids in text
        assert "page_1" not in text
        assert "page_2" not in text
        assert "Open tasks: 1" in text
        assert "1. Write report" in text

        rm = kwargs.get("reply_markup") or {}
        assert "inline_keyboard" in rm
        assert rm["inline_keyboard"][0][0]["callback_data"] == "pick_done"
        assert rm["inline_keyboard"][0][1]["callback_data"] == "pick_edit"

        called["n"] += 1
        return {"ok": True}

    monkeypatch.setattr(main, "edit_telegram_message", fake_edit)

    client = TestClient(main.app)
    update = {
        "update_id": 1,
        "callback_query": {
            "id": "cbq_123",
            "from": {"id": 9},
            "data": "done|task_id=page_1",  # normalize_update will still parse callback; handle_event mocked anyway
            "message": {"message_id": 77, "chat": {"id": 555}},
        },
    }

    r = client.post("/telegram/webhook", json=update)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert called["n"] == 1
