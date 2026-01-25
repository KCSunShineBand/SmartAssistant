from fastapi.testclient import TestClient
import main


def test_edit_action_rerenders_from_cache(monkeypatch):
    # Seed cache like a previous /today render
    main.STATE.render_cache[(555, 777)] = {
        "list_kind": "today",
        "tasks": [
            {"id": "page_1", "title": "Pay rent", "due": None, "status": "todo"},
            {"id": "page_2", "title": "Write report", "due": None, "status": "doing"},
        ],
        "text": "Open tasks: 2 ...",
    }

    monkeypatch.setattr(
        main,
        "handle_event",
        lambda event, state: [
            {"type": "edit", "chat_id": 555, "message_id": 777, "remove_task_id": "page_1"}
        ],
    )

    called = {}

    def fake_edit(chat_id: int, message_id: int, text: str, **kwargs):
        called["chat_id"] = chat_id
        called["message_id"] = message_id
        called["text"] = text
        called["reply_markup"] = kwargs.get("reply_markup")
        return {"ok": True}

    monkeypatch.setattr(main, "edit_telegram_message", fake_edit)

    client = TestClient(main.app)
    update = {
        "update_id": 1,
        "callback_query": {
            "id": "cbq_123",
            "from": {"id": 9},
            "data": "done|task_id=page_1",
            "message": {"message_id": 777, "chat": {"id": 555}},
        },
    }

    r = client.post("/telegram/webhook", json=update)
    assert r.status_code == 200

    assert called["chat_id"] == 555
    assert called["message_id"] == 777

    # New UX: edited message should NOT leak Notion IDs
    assert "page_1" not in called["text"]
    assert "page_2" not in called["text"]

    # Should show remaining task by title in numbered format
    assert "Open tasks: 1" in called["text"]
    assert "1. Write report" in called["text"]

    # Should still have buttons (1 row left)
    # New UX: should still have 2 buttons (Done/Edit)
    rm = called.get("reply_markup") or {}
    assert "inline_keyboard" in rm
    assert len(rm["inline_keyboard"]) == 1
    row0 = rm["inline_keyboard"][0]
    assert row0[0]["callback_data"] == "pick_done"
    assert row0[0]["text"] == "Done"
    assert row0[1]["callback_data"] == "pick_edit"
    assert row0[1]["text"] == "Edit"

