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

NOTION_ENV_KEYS = (
    "NOTION_TOKEN",
    "NOTION_TASKS_DB_ID",
    "NOTION_NOTES_DB_ID",
    "NOTION_VERSION",
)

@pytest.fixture(autouse=True)
def _isolate_tests_from_real_notion(monkeypatch):
    """
    Unit tests must never call the real Notion API.
    Tests that need Notion env vars must set them explicitly via monkeypatch.setenv().
    """
    for k in NOTION_ENV_KEYS:
        monkeypatch.delenv(k, raising=False)

    # Optional: keep behavior deterministic unless a test overrides it
    monkeypatch.setenv("APP_ENV", "test")
