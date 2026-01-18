import os
import pytest

import db


pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")


def _cleanup(chat_id: int):
    # keep tests deterministic
    with db.connect() as conn:
        conn.execute("DELETE FROM tasks WHERE chat_id = %s;", (chat_id,))
        conn.execute("DELETE FROM notes WHERE chat_id = %s;", (chat_id,))


def test_notes_and_tasks_crud():
    db.init_db()
    chat_id = 999001
    _cleanup(chat_id)

    n1 = db.create_note(chat_id, "hello note")
    t1 = db.create_task(chat_id, "buy milk")

    open_tasks = db.list_open_tasks(chat_id, limit=10)
    assert any(t["id"] == t1 and t["done"] is False for t in open_tasks)

    ok = db.mark_task_done(chat_id, t1)
    assert ok is True

    open_tasks2 = db.list_open_tasks(chat_id, limit=10)
    assert all(t["id"] != t1 for t in open_tasks2)


def test_search_notes_tasks():
    db.init_db()
    chat_id = 999002
    _cleanup(chat_id)

    db.create_note(chat_id, "I love chicken rice")
    db.create_task(chat_id, "buy chicken rice")

    hits = db.search_notes_tasks(chat_id, "chicken", limit=10)
    kinds = {h["kind"] for h in hits}
    assert "note" in kinds
    assert "task" in kinds
