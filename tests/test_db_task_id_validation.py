import os
import pytest
import db

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")


def test_mark_task_done_invalid_uuid_returns_false_not_error():
    db.init_db()
    # Should not throw
    ok = db.mark_task_done(123, "task_999")
    assert ok is False
