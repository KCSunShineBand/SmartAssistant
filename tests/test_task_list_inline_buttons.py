import core
import notion
from ui import route_text


def test_today_in_notion_mode_returns_done_and_edit_buttons(monkeypatch):
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

    # Verify message text is numbered and hides IDs
    txt = actions[0].get("text") or ""
    assert "Open tasks: 2" in txt
    assert "1. Pay rent" in txt
    assert "2. Write report" in txt
    assert "page_1" not in txt
    assert "page_2" not in txt

    rm = actions[0].get("reply_markup")
    assert rm and "inline_keyboard" in rm

    # New UX: only 1 row, 2 buttons
    assert len(rm["inline_keyboard"]) == 1
    row0 = rm["inline_keyboard"][0]
    assert len(row0) == 2
    assert row0[0]["text"] == "Done"
    assert row0[0]["callback_data"] == "pick_done"
    assert row0[1]["text"] == "Edit"
    assert row0[1]["callback_data"] == "pick_edit"


def test_inbox_in_notion_mode_returns_done_and_edit_buttons(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_NOTES_DB_ID", "notes_db")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "tasks_db")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    monkeypatch.setattr(
        core.notion,
        "list_inbox_tasks",
        lambda db_id, limit=20: [
            # New UI uses Title + Description; status isn't shown in text anymore
            {"id": "page_A", "title": "Buy milk", "description": "2 litres", "due": None, "status": "todo"},
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

    # Verify message text is numbered and hides IDs
    txt = actions[0].get("text") or ""
    assert "Inbox (open tasks):" in txt
    assert "1. Buy milk | 2 litres" in txt

    # Old UI should NOT appear anymore
    assert "[todo]" not in txt
    assert "page_A" not in txt  # IDs should not show

    # Verify Done/Edit buttons exist
    rm = actions[0].get("reply_markup") or {}
    kb = rm.get("inline_keyboard") or []
    assert kb and len(kb[0]) == 2
    assert kb[0][0].get("text") == "Done"
    assert kb[0][1].get("text") == "Edit"
