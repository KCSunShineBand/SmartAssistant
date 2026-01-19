import core


def test_settings_shows_defaults_when_db_disabled(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    st = core.AppState()
    actions = core.handle_event(
        {
            "type": "message",
            "chat_id": 1,
            "text": "/settings",
            "route": {"kind": "command", "command": "settings"},
        },
        st,
    )
    assert "Settings:" in actions[0]["text"]
    assert "Asia/Singapore" in actions[0]["text"]
    assert "07:30" in actions[0]["text"]


def test_settings_set_writes_to_db(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://whatever")

    monkeypatch.setattr(core.db, "init_db", lambda: None)

    writes = {}
    monkeypatch.setattr(core.db, "set_setting", lambda k, v: writes.update({k: v}))
    monkeypatch.setattr(core.db, "get_setting", lambda k, default=None: default)

    st = core.AppState()
    actions = core.handle_event(
        {
            "type": "message",
            "chat_id": 1,
            "text": "/settings set daily_brief_time 08:15",
            "route": {"kind": "command", "command": "settings"},
        },
        st,
    )

    assert "Updated daily_brief_time" in actions[0]["text"]
    assert writes["daily_brief_time"] == "08:15"


def test_settings_set_validates_ai_enabled(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://whatever")
    monkeypatch.setattr(core.db, "init_db", lambda: None)
    monkeypatch.setattr(core.db, "set_setting", lambda k, v: None)
    monkeypatch.setattr(core.db, "get_setting", lambda k, default=None: default)

    st = core.AppState()
    actions = core.handle_event(
        {
            "type": "message",
            "chat_id": 1,
            "text": "/settings set ai_enabled maybe",
            "route": {"kind": "command", "command": "settings"},
        },
        st,
    )
    assert "ai_enabled must be true/false" in actions[0]["text"]
