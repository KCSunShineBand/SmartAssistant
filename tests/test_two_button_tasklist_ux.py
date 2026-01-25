import os
import pytest

import core


def _set_notion_env(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "x")
    monkeypatch.setenv("NOTION_NOTES_DB_ID", "notes_db")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "tasks_db")


def test_today_renders_two_buttons(monkeypatch):
    _set_notion_env(monkeypatch)

    monkeypatch.setattr(core.notion, "list_open_tasks", lambda db_id, limit=5: [
        {"id": "t1", "title": "Task 1", "due": None, "status": "todo"},
        {"id": "t2", "title": "Task 2", "due": "2026-01-25", "status": "todo"},
    ])

    state = core.AppState()
    event = {
        "type": "message",
        "chat_id": 123,
        "user_id": 999,
        "message_id": 1,
        "text": "/today",
        "route": {"kind": "command", "command": "today"},
    }

    actions = core.handle_event(event, state)
    assert len(actions) == 2

    reply = actions[0]
    assert reply["type"] == "reply"
    kb = reply["reply_markup"]["inline_keyboard"]
    assert kb[0][0]["text"] == "Done"
    assert kb[0][0]["callback_data"] == "pick_done"
    assert kb[0][1]["text"] == "Edit"
    assert kb[0][1]["callback_data"] == "pick_edit"


def test_pick_done_flow_marks_done_and_edits(monkeypatch):
    _set_notion_env(monkeypatch)

    called = {"id": None}
    monkeypatch.setattr(core.notion, "mark_task_done", lambda pid: called.__setitem__("id", pid) or True)

    state = core.AppState()
    chat_id = 123
    list_mid = 99

    state.render_cache[(chat_id, list_mid)] = {
        "list_kind": "today",
        "tasks": [
            {"id": "t1", "title": "Task 1", "due": None, "status": "todo"},
            {"id": "t2", "title": "Task 2", "due": None, "status": "todo"},
        ],
        "text": "Open tasks...",
    }

    # click Done
    cb = {
        "type": "callback",
        "chat_id": chat_id,
        "user_id": 999,
        "message_id": list_mid,
        "callback": {"action": "pick_done", "params": {}},
    }
    actions = core.handle_event(cb, state)
    assert actions and actions[0]["type"] == "reply"
    assert state.pending[chat_id]["mode"] == "done_pick"

    # reply "2"
    msg = {
        "type": "message",
        "chat_id": chat_id,
        "user_id": 999,
        "message_id": 100,
        "text": "2",
        "route": {"kind": "text", "text": "2"},
    }
    actions2 = core.handle_event(msg, state)
    assert actions2 and actions2[0]["type"] == "edit"
    assert actions2[0]["remove_task_id"] == "t2"
    assert called["id"] == "t2"
    assert chat_id not in state.pending


def test_pick_edit_flow_updates_title_and_edits(monkeypatch):
    _set_notion_env(monkeypatch)

    called = {"id": None, "title": None}
    def _upd(pid, title):
        called["id"] = pid
        called["title"] = title
        return True

    monkeypatch.setattr(core.notion, "update_task_title", _upd)

    state = core.AppState()
    chat_id = 123
    list_mid = 77

    state.render_cache[(chat_id, list_mid)] = {
        "list_kind": "today",
        "tasks": [{"id": "t1", "title": "Old", "due": None, "status": "todo"}],
        "text": "Open tasks...",
    }

    cb = {
        "type": "callback",
        "chat_id": chat_id,
        "user_id": 999,
        "message_id": list_mid,
        "callback": {"action": "pick_edit", "params": {}},
    }
    actions = core.handle_event(cb, state)
    assert actions[0]["type"] == "reply"
    assert state.pending[chat_id]["mode"] == "edit_pick"

    msg_pick = {
        "type": "message",
        "chat_id": chat_id,
        "user_id": 999,
        "message_id": 78,
        "text": "1",
        "route": {"kind": "text", "text": "1"},
    }
    actions2 = core.handle_event(msg_pick, state)
    assert actions2[0]["type"] == "reply"
    assert state.pending[chat_id]["mode"] == "edit_new_text"

    msg_new = {
        "type": "message",
        "chat_id": chat_id,
        "user_id": 999,
        "message_id": 79,
        "text": "New Title",
        "route": {"kind": "text", "text": "New Title"},
    }
    actions3 = core.handle_event(msg_new, state)
    assert actions3[0]["type"] == "edit"
    assert actions3[0]["update_task"]["id"] == "t1"
    assert actions3[0]["update_task"]["title"] == "New Title"
    assert called["id"] == "t1"
    assert called["title"] == "New Title"
    assert chat_id not in state.pending
