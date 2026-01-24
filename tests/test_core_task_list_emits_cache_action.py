import core
from ui import route_text


def test_today_notion_emits_cache_task_list_action(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_NOTES_DB_ID", "notes_db")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "tasks_db")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    monkeypatch.setattr(
        core.notion,
        "list_open_tasks",
        lambda db_id, limit=5: [
            {"id": "page_1", "title": "Pay rent", "due": "2026-01-21", "status": "todo"},
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
    assert len(actions) == 2
    assert actions[0]["type"] == "reply"
    assert actions[1]["type"] == "cache_task_list"
    assert actions[1]["list_kind"] == "today"
    assert actions[1]["tasks"][0]["id"] == "page_1"
