import pytest

from ui import route_text


def test_route_plain_text():
    assert route_text("hello") == {"kind": "text", "text": "hello"}


def test_route_trims_text():
    assert route_text("  hello  ") == {"kind": "text", "text": "hello"}


def test_route_note_command():
    r = route_text("/note buy milk")
    assert r["kind"] == "command"
    assert r["command"] == "note"
    assert r["text"] == "buy milk"


def test_route_note_command_with_botname():
    r = route_text("/note@SomeBot buy milk")
    assert r["kind"] == "command"
    assert r["command"] == "note"
    assert r["text"] == "buy milk"


def test_route_todo_command():
    r = route_text("/todo submit report")
    assert r["kind"] == "command"
    assert r["command"] == "todo"
    assert r["text"] == "submit report"


def test_route_today_command_no_args():
    r = route_text("/today")
    assert r == {"kind": "command", "command": "today", "args": ""}


def test_route_done_parses_task_id():
    r = route_text("/done task_123 extra words ignored")
    assert r["kind"] == "command"
    assert r["command"] == "done"
    assert r["task_id"] == "task_123"


def test_route_search_requires_args():
    r = route_text("/search")
    assert r["kind"] == "error"
    assert r["error"] == "missing_args_search"


def test_unknown_command():
    r = route_text("/wat is this")
    assert r["kind"] == "unknown_command"
    assert r["command"] == "wat"


def test_invalid_input():
    r = route_text(None)  # type: ignore[arg-type]
    assert r["kind"] == "error"
    assert r["error"] == "invalid_input"
