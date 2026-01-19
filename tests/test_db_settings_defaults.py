import uuid
import pytest

import db


def _ensure_db_or_skip():
    try:
        db.init_db()
    except Exception as e:
        pytest.skip(f"DB not available for tests: {e}")


def test_get_setting_returns_default_when_missing():
    _ensure_db_or_skip()

    missing_key = f"missing_{uuid.uuid4()}"
    assert db.get_setting(missing_key, "07:30") == "07:30"


def test_get_setting_returns_none_when_missing_and_no_default():
    _ensure_db_or_skip()

    missing_key = f"missing_{uuid.uuid4()}"
    assert db.get_setting(missing_key) is None


def test_set_setting_then_get_setting():
    _ensure_db_or_skip()

    k = f"test_key_{uuid.uuid4()}"
    db.set_setting(k, "A")
    assert db.get_setting(k, "B") == "A"
