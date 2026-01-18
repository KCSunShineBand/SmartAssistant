import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import init_db, save_message_map, get_notion_page_id


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_save_and_get_message_map_upsert():
    init_db()

    chat_id = 123456
    msg_id = 10

    assert get_notion_page_id(chat_id, msg_id) is None

    save_message_map(chat_id, msg_id, "page_1")
    assert get_notion_page_id(chat_id, msg_id) == "page_1"

    # overwrite
    save_message_map(chat_id, msg_id, "page_2")
    assert get_notion_page_id(chat_id, msg_id) == "page_2"
