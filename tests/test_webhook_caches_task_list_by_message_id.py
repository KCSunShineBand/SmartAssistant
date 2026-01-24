import main
from fastapi.testclient import TestClient


def test_webhook_stores_render_cache_using_sent_message_id(monkeypatch):
    # Reset global state cache
    if hasattr(main.STATE, "render_cache"):
        main.STATE.render_cache.clear()

    # handle_event returns reply + cache action
    monkeypatch.setattr(
        main,
        "handle_event",
        lambda event, state: [
            {
                "type": "reply",
                "chat_id": 555,
                "text": "Open tasks: 1\n- page_1: Pay rent",
                "reply_markup": {"inline_keyboard": [[{"text": "✅ Done", "callback_data": "done|task_id=page_1"}]]},
            },
            {
                "type": "cache_task_list",
                "chat_id": 555,
                "list_kind": "today",
                "tasks": [{"id": "page_1", "title": "Pay rent", "due": None, "status": "todo"}],
                "text": "Open tasks: 1\n- page_1: Pay rent",
            },
        ],
    )

    # send_telegram_message returns Telegram-like JSON including message_id
    monkeypatch.setattr(
        main,
        "send_telegram_message",
        lambda chat_id, text, **kwargs: {"ok": True, "result": {"message_id": 777}},
    )

    client = TestClient(main.app)
    update = {"update_id": 1, "message": {"message_id": 1, "chat": {"id": 555}, "from": {"id": 9}, "text": "/today"}}
    r = client.post("/telegram/webhook", json=update)
    assert r.status_code == 200

    assert hasattr(main.STATE, "render_cache")
    key = (555, 777)
    assert key in main.STATE.render_cache
    assert main.STATE.render_cache[key]["list_kind"] == "today"
    assert main.STATE.render_cache[key]["tasks"][0]["id"] == "page_1"
