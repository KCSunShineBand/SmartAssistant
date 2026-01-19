import core


def test_notion_note_saves_message_map_when_db_enabled(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_NOTES_DB_ID", "notesdb")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "tasksdb")
    monkeypatch.setenv("DATABASE_URL", "postgresql://whatever")  # enable db_enabled path

    monkeypatch.setattr(core.notion, "create_note", lambda *a, **k: "note-page-123")

    monkeypatch.setattr(core.db, "init_db", lambda: None)

    saved = {}

    def fake_save_message_map(message_id, kind, notion_page_id, chat_id, user_id=None):
        saved["message_id"] = message_id
        saved["kind"] = kind
        saved["notion_page_id"] = notion_page_id
        saved["chat_id"] = chat_id
        saved["user_id"] = user_id

    monkeypatch.setattr(core.db, "save_message_map", fake_save_message_map)

    st = core.AppState()
    actions = core.handle_event(
        {
            "type": "message",
            "chat_id": 1,
            "user_id": 9,
            "message_id": 777,
            "text": "hello",
            "route": {"kind": "text", "text": "hello"},
        },
        st,
    )

    assert actions[0]["type"] == "reply"
    assert saved["message_id"] == 777
    assert saved["kind"] == "note"
    assert saved["notion_page_id"] == "note-page-123"
    assert saved["chat_id"] == 1
    assert saved["user_id"] == 9


def test_notion_task_saves_message_map_when_db_enabled(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_NOTES_DB_ID", "notesdb")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "tasksdb")
    monkeypatch.setenv("DATABASE_URL", "postgresql://whatever")  # enable db_enabled path

    monkeypatch.setattr(core.notion, "create_task", lambda *a, **k: "task-page-999")

    monkeypatch.setattr(core.db, "init_db", lambda: None)

    saved = {}

    monkeypatch.setattr(
        core.db,
        "save_message_map",
        lambda message_id, kind, notion_page_id, chat_id, user_id=None: saved.update(
            {
                "message_id": message_id,
                "kind": kind,
                "notion_page_id": notion_page_id,
                "chat_id": chat_id,
                "user_id": user_id,
            }
        ),
    )

    st = core.AppState()
    actions = core.handle_event(
        {
            "type": "message",
            "chat_id": 1,
            "user_id": 9,
            "message_id": 888,
            "text": "/todo buy milk",
            "route": {"kind": "command", "command": "todo", "text": "buy milk"},
        },
        st,
    )

    assert actions[0]["type"] == "reply"
    assert saved["message_id"] == 888
    assert saved["kind"] == "task"
    assert saved["notion_page_id"] == "task-page-999"
    assert saved["chat_id"] == 1
    assert saved["user_id"] == 9
