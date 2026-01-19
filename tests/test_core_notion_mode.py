import core


def test_note_uses_notion_when_configured(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_NOTES_DB_ID", "notesdb")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "tasksdb")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    # If DB note creation is called, fail
    monkeypatch.setattr(core.db, "create_note", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("db.create_note should NOT be called in Notion mode")
    ))

    calls = {}

    def fake_create_note(db_id, **kwargs):
        calls["db_id"] = db_id
        calls["kwargs"] = kwargs
        return "note-page-123"

    monkeypatch.setattr(core.notion, "create_note", fake_create_note)

    st = core.AppState()
    actions = core.handle_event(
        {
            "type": "message",
            "chat_id": 1,
            "text": "/note hello world",
            "route": {"kind": "command", "command": "note", "text": "hello world"},
        },
        st,
    )

    assert actions[0]["type"] == "reply"
    assert "Saved note (Notion): note-page-123" in actions[0]["text"]
    assert calls["db_id"] == "notesdb"
    assert calls["kwargs"]["text"] == "hello world"


def test_todo_uses_notion_when_configured(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_NOTES_DB_ID", "notesdb")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "tasksdb")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    monkeypatch.setattr(core.db, "create_task", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("db.create_task should NOT be called in Notion mode")
    ))

    calls = {}

    def fake_create_task(db_id, **kwargs):
        calls["db_id"] = db_id
        calls["kwargs"] = kwargs
        return "task-page-999"

    monkeypatch.setattr(core.notion, "create_task", fake_create_task)

    st = core.AppState()
    actions = core.handle_event(
        {
            "type": "message",
            "chat_id": 1,
            "text": "/todo buy milk",
            "route": {"kind": "command", "command": "todo", "text": "buy milk"},
        },
        st,
    )

    assert actions[0]["type"] == "reply"
    assert "Added task (Notion): task-page-999" in actions[0]["text"]
    assert calls["db_id"] == "tasksdb"
    assert calls["kwargs"]["title"] == "buy milk"

def test_today_uses_notion_when_configured(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_NOTES_DB_ID", "notesdb")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "tasksdb")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    monkeypatch.setattr(core.notion, "list_open_tasks", lambda dbid, limit=5: [{"id": "t1", "title": "X", "due": None}])

    st = core.AppState()
    actions = core.handle_event(
        {
            "type": "message",
            "chat_id": 1,
            "user_id": 9,
            "message_id": 1,
            "text": "/today",
            "route": {"kind": "command", "command": "today"},
        },
        st,
    )
    assert "Open tasks:" in actions[0]["text"]


def test_done_uses_notion_when_configured(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_NOTES_DB_ID", "notesdb")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "tasksdb")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    called = {"id": None}
    monkeypatch.setattr(core.notion, "mark_task_done", lambda pid: called.update({"id": pid}) or True)

    st = core.AppState()
    actions = core.handle_event(
        {
            "type": "message",
            "chat_id": 1,
            "user_id": 9,
            "message_id": 2,
            "text": "/done abc",
            "route": {"kind": "command", "command": "done", "task_id": "abc"},
        },
        st,
    )
    assert called["id"] == "abc"
    assert "Marked done (Notion)" in actions[0]["text"]
