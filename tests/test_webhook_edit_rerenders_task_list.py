import main
from fastapi.testclient import TestClient


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

    monkeypatch.setattr(main, "handle_event", lambda event, state: [
        {"type": "edit", "chat_id": 555, "message_id": 777, "remove_task_id": "page_1"}
    ])

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
    assert "page_1" not in called["text"]
    assert "page_2" in called["text"]
    rm = called["reply_markup"]
    assert rm and "inline_keyboard" in rm
    # should now be 1 row left
    assert len(rm["inline_keyboard"]) == 1

    # cache should now only contain page_2
    cached = main.STATE.render_cache[(555, 777)]
    assert len(cached["tasks"]) == 1
    assert cached["tasks"][0]["id"] == "page_2"
