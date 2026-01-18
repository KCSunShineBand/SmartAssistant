import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import init_db, get_setting, set_setting, get_bool_setting


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_settings_set_and_get():
    init_db()

    set_setting("timezone", "Asia/Singapore")
    assert get_setting("timezone") == "Asia/Singapore"

    # overwrite
    set_setting("timezone", "UTC")
    assert get_setting("timezone") == "UTC"


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_get_bool_setting_parsing():
    init_db()

    set_setting("auto_structure", "true")
    assert get_bool_setting("auto_structure", default=False) is True

    set_setting("auto_structure", "0")
    assert get_bool_setting("auto_structure", default=True) is False

    set_setting("auto_structure", "maybe")
    assert get_bool_setting("auto_structure", default=True) is True
