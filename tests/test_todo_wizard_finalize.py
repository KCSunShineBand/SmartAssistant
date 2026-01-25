import core
from ui import route_text


def _set_notion_env(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_NOTES_DB_ID", "notesdb")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "tasksdb")
    monkeypatch.delenv("DATABASE_URL", raising=False)


def test_todo_wizard_need_desc_finalizes_in_same_message(monkeypatch):
    _set_notion_env(monkeypatch)

    captured = {"title": None, "desc": None}

    def fake_create_task(db_id, *, title, description=None, **kwargs):
        captured["title"] = title
        captured["desc"] = description or ""
        return "page_123"

    monkeypatch.setattr(core.notion, "create_task", fake_create_task)

    st = core.AppState()

    # Seed wizard as if user already picked a Title and we are now waiting for Description
    st.todo_wizard[1] = {"stage": "need_desc", "title": "Grocery"}

    ev = {
        "type": "message",
        "chat_id": 1,
        "user_id": 9,
        "message_id": 10,
        "text": "Buy milk",
        "route": route_text("Buy milk"),
    }

    actions = core.handle_event(ev, st)

    assert actions and actions[0]["type"] == "reply"
    assert "Added: Grocery | Buy milk" in actions[0]["text"]
    assert captured["title"] == "Grocery"
    assert captured["desc"] == "Buy milk"
    assert 1 not in st.todo_wizard  # wizard cleared
