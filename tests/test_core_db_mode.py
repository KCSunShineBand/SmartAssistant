import os
import pytest

from core import AppState, handle_event

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")


def test_core_uses_db_for_task_ids():
    state = AppState()
    out = handle_event(
        {"type": "message", "chat_id": 123, "text": "/todo buy milk", "route": {"kind": "command", "command": "todo", "text": "buy milk"}},
        state,
    )
    msg = out[0]["text"]
    # DB task ids are UUID strings, not "task_1"
    assert "Added task:" in msg
    assert "task_" not in msg
