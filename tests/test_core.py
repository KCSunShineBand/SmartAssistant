import pytest

from core import AppState, handle_event


# These tests validate the in-memory fallback behavior.
# Force-disable DB mode even if DATABASE_URL is set in the shell.
@pytest.fixture(autouse=True)
def _disable_db(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)


def test_plain_text_creates_note():
    state = AppState()
    actions = handle_event(
        {"type": "message", "chat_id": 1, "text": "hello", "route": {"kind": "text", "text": "hello"}},
        state,
    )
    assert actions and actions[0]["type"] == "reply"
    assert len(state.notes[1]) == 1
    assert state.notes[1][0].text == "hello"


def test_todo_and_today():
    state = AppState()
    handle_event(
        {"type": "message", "chat_id": 1, "text": "/todo do x", "route": {"kind": "command", "command": "todo", "text": "do x"}},
        state,
    )
    out = handle_event(
        {"type": "message", "chat_id": 1, "text": "/today", "route": {"kind": "command", "command": "today", "args": ""}},
        state,
    )
    assert "Open tasks: 1" in out[0]["text"]


def test_done_marks_task_done():
    state = AppState()
    handle_event(
        {"type": "message", "chat_id": 1, "text": "/todo do x", "route": {"kind": "command", "command": "todo", "text": "do x"}},
        state,
    )
    task_id = state.tasks[1][0].id
    out = handle_event(
        {"type": "message", "chat_id": 1, "text": f"/done {task_id}", "route": {"kind": "command", "command": "done", "task_id": task_id}},
        state,
    )
    assert "Marked done" in out[0]["text"]
    assert state.tasks[1][0].done is True


def test_done_unknown_task():
    state = AppState()
    out = handle_event(
        {"type": "message", "chat_id": 1, "text": "/done task_999", "route": {"kind": "command", "command": "done", "task_id": "task_999"}},
        state,
    )
    assert "Task not found" in out[0]["text"]
