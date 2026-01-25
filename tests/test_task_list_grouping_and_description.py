import os
import core
from ui import route_text


def _set_notion_env(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_NOTES_DB_ID", "notes_db")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "tasks_db")
    monkeypatch.delenv("DATABASE_URL", raising=False)


def test_today_groups_by_title_and_shows_description(monkeypatch):
    _set_notion_env(monkeypatch)

    # Intentionally out of order: Grocery, Work, Grocery
    monkeypatch.setattr(
        core.notion,
        "list_open_tasks",
        lambda db_id, limit=5: [
            {"id": "p1", "title": "Grocery", "description": "Buy Milk", "due": None, "status": "todo"},
            {"id": "p2", "title": "Work", "description": "Print Payslip", "due": None, "status": "doing"},
            {"id": "p3", "title": "Grocery", "description": "Buy Eggs x 2", "due": None, "status": "todo"},
        ],
    )

    st = core.AppState()
    ev = {
        "type": "message",
        "chat_id": 1,
        "user_id": 9,
        "message_id": 10,
        "text": "/today",
        "route": route_text("/today"),
    }

    actions = core.handle_event(ev, st)
    assert actions and actions[0]["type"] == "reply"
    txt = actions[0]["text"]

    assert "Open tasks: 3" in txt

    # Must be grouped by Title then Description
    # Grocery group first, then Work
    assert "1. Grocery | Buy Eggs x 2" in txt
    assert "2. Grocery | Buy Milk" in txt
    assert "3. Work | Print Payslip" in txt

    # Should not leak IDs
    assert "p1" not in txt
    assert "p2" not in txt
    assert "p3" not in txt


def test_inbox_groups_by_title_and_shows_description(monkeypatch):
    _set_notion_env(monkeypatch)

    monkeypatch.setattr(
        core.notion,
        "list_inbox_tasks",
        lambda db_id, limit=20: [
            {"id": "a1", "title": "work", "description": "Email boss", "due": None, "status": "todo"},
            {"id": "a2", "title": "Bills", "description": "Pay SP", "due": None, "status": "todo"},
            {"id": "a3", "title": "Work", "description": "Submit report", "due": None, "status": "doing"},
        ],
    )

    st = core.AppState()
    ev = {
        "type": "message",
        "chat_id": 1,
        "user_id": 9,
        "message_id": 11,
        "text": "/inbox",
        "route": route_text("/inbox"),
    }

    actions = core.handle_event(ev, st)
    assert actions and actions[0]["type"] == "reply"
    txt = actions[0]["text"]

    assert "Inbox (open tasks):" in txt

    # Bills first, then Work (work/Work grouped case-insensitive)
    assert "1. Bills | Pay SP" in txt
    # Within Work group, description alpha order: Email boss, Submit report
    assert "2. work | Email boss" in txt or "2. Work | Email boss" in txt
    assert "3. Work | Submit report" in txt or "3. work | Submit report" in txt

    # Should not leak IDs
    assert "a1" not in txt
    assert "a2" not in txt
    assert "a3" not in txt
