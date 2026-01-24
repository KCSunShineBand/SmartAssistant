import core
import notion
from ui import route_text


def test_note_reply_includes_open_in_notion_button(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_NOTES_DB_ID", "notes_db")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "tasks_db")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    monkeypatch.setattr(core.notion, "create_note", lambda *args, **kwargs: "11111111-1111-1111-1111-111111111111")

    ev = {
        "type": "message",
        "chat_id": 1,
        "user_id": 2,
        "message_id": 10,
        "text": "/note hello",
        "route": route_text("/note hello"),
    }

    actions = core.handle_event(ev, core.AppState())
    assert actions and actions[0]["type"] == "reply"

    rm = actions[0].get("reply_markup")
    assert rm and "inline_keyboard" in rm
    assert rm["inline_keyboard"][0][0]["text"] == "Open in Notion"
    assert rm["inline_keyboard"][0][0]["url"] == notion.page_url("11111111-1111-1111-1111-111111111111")


def test_todo_reply_includes_open_in_notion_button(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_NOTES_DB_ID", "notes_db")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "tasks_db")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    monkeypatch.setattr(core.notion, "create_task", lambda *args, **kwargs: "22222222-2222-2222-2222-222222222222")

    ev = {
        "type": "message",
        "chat_id": 1,
        "user_id": 2,
        "message_id": 11,
        "text": "/todo buy milk",
        "route": route_text("/todo buy milk"),
    }

    actions = core.handle_event(ev, core.AppState())
    assert actions and actions[0]["type"] == "reply"

    rm = actions[0].get("reply_markup")
    assert rm and "inline_keyboard" in rm
    assert rm["inline_keyboard"][0][0]["text"] == "Open in Notion"
    assert rm["inline_keyboard"][0][0]["url"] == notion.page_url("22222222-2222-2222-2222-222222222222")
