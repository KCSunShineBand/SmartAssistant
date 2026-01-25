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

    monkeypatch.setattr(
        core.notion,
        "create_task",
        lambda *args, **kwargs: "22222222-2222-2222-2222-222222222222",
    )

    st = core.AppState()

    # Step 1: /todo title -> wizard asks for Description (no button yet)
    ev1 = {
        "type": "message",
        "chat_id": 1,
        "user_id": 2,
        "message_id": 11,
        "text": "/todo buy milk",
        "route": route_text("/todo buy milk"),
    }
    actions1 = core.handle_event(ev1, st)
    assert actions1 and actions1[0]["type"] == "reply"
    assert "Send the Description" in (actions1[0].get("text") or "")
    assert actions1[0].get("reply_markup") is None

    # Step 2: Description -> task created -> reply should include Open in Notion button
    ev2 = {
        "type": "message",
        "chat_id": 1,
        "user_id": 2,
        "message_id": 12,
        "text": "2 litres",
        "route": {"kind": "text", "text": "2 litres"},
    }
    actions2 = core.handle_event(ev2, st)

    assert actions2 and actions2[0]["type"] == "reply"
    rm = actions2[0].get("reply_markup")
    assert rm and "inline_keyboard" in rm

    btn = rm["inline_keyboard"][0][0]
    assert btn["text"] == "Open in Notion"
    assert "notion.so" in btn["url"]
