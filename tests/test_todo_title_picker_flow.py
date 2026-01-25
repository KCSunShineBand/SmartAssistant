import core
from ui import route_text


def _set_notion_env(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_NOTES_DB_ID", "notesdb")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "tasksdb")
    monkeypatch.delenv("DATABASE_URL", raising=False)


def test_todo_starts_title_picker(monkeypatch):
    _set_notion_env(monkeypatch)

    monkeypatch.setattr(core.notion, "list_unique_task_titles", lambda db_id, limit=20: ["Grocery", "Work"])

    st = core.AppState()
    ev = {
        "type": "message",
        "chat_id": 1,
        "user_id": 9,
        "message_id": 1,
        "text": "/todo",
        "route": route_text("/todo"),
    }

    actions = core.handle_event(ev, st)
    assert actions and actions[0]["type"] == "reply"
    txt = actions[0]["text"]
    assert "0. New Title" in txt
    assert "1. Grocery" in txt
    assert "2. Work" in txt
    assert st.todo_wizard[1]["stage"] == "pick_title"


def test_todo_power_user_inline_format_creates(monkeypatch):
    _set_notion_env(monkeypatch)

    captured = {"title": None, "desc": None}

    def fake_create_task(db_id, *, title, description=None, **kwargs):
        captured["title"] = title
        captured["desc"] = description or ""
        return "page_999"

    monkeypatch.setattr(core.notion, "create_task", fake_create_task)

    st = core.AppState()
    ev = {
        "type": "message",
        "chat_id": 1,
        "user_id": 9,
        "message_id": 10,
        "text": "/todo Grocery | Buy eggs x2",
        "route": route_text("/todo Grocery | Buy eggs x2"),
    }

    actions = core.handle_event(ev, st)
    assert actions and actions[0]["type"] == "reply"
    assert "Added: Grocery | Buy eggs x2" in actions[0]["text"]
    assert captured["title"] == "Grocery"
    assert captured["desc"] == "Buy eggs x2"
