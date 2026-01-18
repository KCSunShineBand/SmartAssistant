import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import init_db, connect


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_init_db_creates_tables_and_vector_extension():
    init_db()

    with connect() as conn:
        ext = conn.execute(
            "SELECT extname FROM pg_extension WHERE extname = 'vector';"
        ).fetchone()
        assert ext is not None

        expected = {
            "settings",
            "labels",
            "telegram_message_map",
            "embedding_chunks",
            "job_queue",
        }
        rows = conn.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = ANY(%s);
            """,
            (list(expected),),
        ).fetchall()

        found = {r[0] for r in rows}
        assert expected.issubset(found)
