import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import init_db, connect


@pytest.fixture(autouse=True)
def _clean_db_per_test():
    """
    Ensures test isolation when using a persistent Postgres container.
    Runs before every test (autouse).
    """
    if not os.getenv("DATABASE_URL"):
        yield
        return

    init_db()
    with connect(register_pgvector=False) as conn:
        conn.execute(
            """
            TRUNCATE
              job_queue,
              telegram_message_map,
              settings,
              labels,
              embedding_chunks
            RESTART IDENTITY;
            """
        )
    yield

