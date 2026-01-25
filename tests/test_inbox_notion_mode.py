import core


def test_inbox_uses_notion_when_configured(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_NOTES_DB_ID", "notesdb")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "tasksdb")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    # New UI spec: "N. Title | Description"
    # Also: status is NOT shown in the output anymore.
    monkeypatch.setattr(
        core.notion,
        "list_inbox_tasks",
        lambda dbid, limit=20: [
            {"id": "t1", "title": "Buy milk", "description": "2 litres", "status": "todo", "due": "2026-01-20"},
            {"id": "t2", "title": "Send invoice", "description": "Jan 2026", "status": "doing", "due": None},
        ],
    )

    st = core.AppState()
    actions = core.handle_event(
        {
            "type": "message",
            "chat_id": 1,
            "user_id": 9,
            "message_id": 1,
            "text": "/inbox",
            "route": {"kind": "command", "command": "inbox"},
        },
        st,
    )

    assert actions[0]["type"] == "reply"
    txt = actions[0]["text"]

    assert "Inbox (open tasks)" in txt
    assert "1. Buy milk | 2 litres" in txt
    assert "2. Send invoice | Jan 2026" in txt

    # Old UI should NOT appear anymore
    assert "[doing]" not in txt
    assert "[todo]" not in txt



def test_inbox_empty(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_NOTES_DB_ID", "notesdb")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "tasksdb")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    monkeypatch.setattr(core.notion, "list_inbox_tasks", lambda dbid, limit=20: [])

    st = core.AppState()
    actions = core.handle_event(
        {
            "type": "message",
            "chat_id": 1,
            "user_id": 9,
            "message_id": 1,
            "text": "/inbox",
            "route": {"kind": "command", "command": "inbox"},
        },
        st,
    )

    assert "Inbox is empty" in actions[0]["text"]
