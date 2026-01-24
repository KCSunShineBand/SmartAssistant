import core
import notion
from ui import route_text


def test_today_in_notion_mode_returns_done_and_open_buttons(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_NOTES_DB_ID", "notes_db")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "tasks_db")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    monkeypatch.setattr(
        core.notion,
        "list_open_tasks",
        lambda db_id, limit=5: [
            {"id": "page_1", "title": "Pay rent", "due": "2026-01-21", "status": "todo"},
            {"id": "page_2", "title": "Write report", "due": None, "status": "doing"},
        ],
    )

    ev = {
        "type": "message",
        "chat_id": 1,
        "user_id": 2,
        "message_id": 10,
        "text": "/today",
        "route": route_text("/today"),
    }

    actions = core.handle_event(ev, core.AppState())
    assert actions and actions[0]["type"] == "reply"
    rm = actions[0].get("reply_markup")
    assert rm and "inline_keyboard" in rm
    assert len(rm["inline_keyboard"]) == 2

    row0 = rm["inline_keyboard"][0]
    assert row0[0]["text"] == "✅ Done"
    assert row0[0]["callback_data"] == "done|task_id=page_1"
    assert row0[1]["text"] == "Open"
    assert row0[1]["url"] == notion.page_url("page_1")


def test_inbox_in_notion_mode_returns_done_and_open_buttons(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_NOTES_DB_ID", "notes_db")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "tasks_db")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    monkeypatch.setattr(
        core.notion,
        "list_inbox_tasks",
        lambda db_id, limit=20: [
            {"id": "page_A", "title": "Buy milk", "due": None, "status": "todo"},
        ],
    )

    ev = {
        "type": "message",
        "chat_id": 1,
        "user_id": 2,
        "message_id": 11,
        "text": "/inbox",
        "route": route_text("/inbox"),
    }

    actions = core.handle_event(ev, core.AppState())
    assert actions and actions[0]["type"] == "reply"
    rm = actions[0].get("reply_markup")
    assert rm and "inline_keyboard" in rm
    assert len(rm["inline_keyboard"]) == 1

    row0 = rm["inline_keyboard"][0]
    assert row0[0]["text"] == "✅ Done"
    assert row0[0]["callback_data"] == "done|task_id=page_A"
    assert row0[1]["text"] == "Open"
    assert row0[1]["url"] == notion.page_url("page_A")
