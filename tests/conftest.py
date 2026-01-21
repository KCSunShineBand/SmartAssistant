import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import init_db, connect

# ---------------------------
# DB safety / determinism
# ---------------------------
RUN_DB_TESTS = os.getenv("RUN_DB_TESTS", "").strip().lower() in {"1", "true", "yes"}

# Make any real DB connect fail fast if someone *does* try (libpq env)
os.environ.setdefault("PGCONNECT_TIMEOUT", "3")


@pytest.fixture(scope="session", autouse=True)
def _disable_db_by_default():
    """
    Prevent accidental Postgres hangs after reboot / env leakage.

    Default: DB is disabled for unit tests.
    Opt-in:  RUN_DB_TESTS=1 pytest -q
    """
    if RUN_DB_TESTS:
        yield
        return

    # Even if DATABASE_URL leaks from your shell, ignore it for unit tests.
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("TEST_DATABASE_URL", None)

    # Hard guard: if anything tries to connect via psycopg, skip instead of hanging.
    import psycopg

    original_connect = psycopg.connect

    def _blocked_connect(*args, **kwargs):
        pytest.skip("DB disabled for unit tests (prevents hangs). Set RUN_DB_TESTS=1 to enable DB tests.")

    psycopg.connect = _blocked_connect
    try:
        yield
    finally:
        psycopg.connect = original_connect


@pytest.fixture(autouse=True)
def _clean_db_per_test():
    """
    Ensures test isolation when using a persistent Postgres container.
    Runs before every test (autouse).

    Only runs when RUN_DB_TESTS=1 AND a DB URL exists.
    """
    if not RUN_DB_TESTS:
        yield
        return

    # Support either env var style
    if not (os.getenv("DATABASE_URL") or os.getenv("TEST_DATABASE_URL")):
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
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)

