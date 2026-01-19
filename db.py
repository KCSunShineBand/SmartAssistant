# db.py
import os
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.types.json import Jsonb
from pgvector.psycopg import register_vector, Vector

import re


import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Iterable

from typing import Sequence


def get_db_url() -> str:
    """
    Source of truth for DB connection.

    Normal runtime:
      - uses DATABASE_URL

    Test runtime (pytest):
      - if TEST_DATABASE_URL is set -> uses TEST_DATABASE_URL
      - else -> defaults to local docker postgres:
          postgresql://postgres:postgres@localhost:5432/smartassistant

    Why:
      - Lets you keep DATABASE_URL pointing to Cloud SQL sockets/URLs for GCP
      - While pytest uses a local DB that actually exists on your laptop
    """
    is_pytest = bool(os.getenv("PYTEST_CURRENT_TEST")) or os.getenv("APP_ENV", "").lower() in {"test", "testing"}

    if is_pytest:
        test_url = os.getenv("TEST_DATABASE_URL", "").strip()
        if test_url:
            return test_url
        # sensible default for local docker-compose dev
        return "postgresql://postgres:postgres@localhost:5432/smartassistant"

    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return url



# db.py
@contextmanager
def connect(register_pgvector: bool = True) -> Iterator[psycopg.Connection]:
    """
    Yields a psycopg3 connection.
    If register_pgvector=True, registers pgvector adapters (requires extension installed).
    """
    conn = psycopg.connect(get_db_url())
    conn.autocommit = True

    if register_pgvector:
        try:
            register_vector(conn)
        except psycopg.ProgrammingError:
            # Happens when pgvector extension isn't created yet.
            # init_db() will create it first, then future connects will register cleanly.
            pass

    try:
        yield conn
    finally:
        conn.close()



# db.py
def init_db() -> None:
    """
    Creates required tables if missing.
    Idempotent.
    Ensures pgvector extension exists BEFORE any vector columns are referenced.
    """
    with connect(register_pgvector=False) as conn:
        # Must exist before any VECTOR type is referenced
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")

        # Now safe to create tables that use VECTOR
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL,
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS labels (
              name TEXT PRIMARY KEY,
              canonical_key TEXT UNIQUE NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS telegram_message_map (
              chat_id BIGINT NOT NULL,
              message_id BIGINT NOT NULL,
              notion_page_id TEXT NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              PRIMARY KEY (chat_id, message_id)
            );

            -- Persistent Notes (MVP)
            CREATE TABLE IF NOT EXISTS notes (
              id UUID PRIMARY KEY,
              chat_id BIGINT NOT NULL,
              text TEXT NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            -- Persistent Tasks (MVP)
            CREATE TABLE IF NOT EXISTS tasks (
              id UUID PRIMARY KEY,
              chat_id BIGINT NOT NULL,
              text TEXT NOT NULL,
              done BOOLEAN NOT NULL DEFAULT FALSE,
              done_at TIMESTAMPTZ,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS embedding_chunks (
              id BIGSERIAL PRIMARY KEY,
              kind TEXT NOT NULL,              -- 'note' | 'task'
              notion_page_id TEXT NOT NULL,
              chunk_index INT NOT NULL,
              content_hash TEXT NOT NULL,
              embedding VECTOR,                -- dimensionless (variable), flexible
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              UNIQUE (kind, notion_page_id, chunk_index, content_hash)
            );

            CREATE TABLE IF NOT EXISTS job_queue (
              id UUID PRIMARY KEY,
              type TEXT NOT NULL,
              payload JSONB NOT NULL,
              status TEXT NOT NULL DEFAULT 'queued',   -- queued|running|done|failed
              run_after TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              retry_count INT NOT NULL DEFAULT 0,
              last_error TEXT,
              locked_at TIMESTAMPTZ,
              created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
              updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_job_queue_status_run_after
              ON job_queue (status, run_after);

            CREATE INDEX IF NOT EXISTS idx_embedding_kind_page
              ON embedding_chunks (kind, notion_page_id);

            CREATE INDEX IF NOT EXISTS idx_notes_chat_created
              ON notes (chat_id, created_at DESC);

            CREATE INDEX IF NOT EXISTS idx_tasks_chat_done_created
              ON tasks (chat_id, done, created_at DESC);
            """
        )



def db_health() -> dict:
    """
    Returns a small dict suitable for a /db/health endpoint later.
    Never throws (captures error and returns ok=False).
    """
    try:
        with connect() as conn:
            row = conn.execute("SELECT 1;").fetchone()
        return {"ok": bool(row and row[0] == 1)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def create_note(chat_id: int, text: str) -> str:
    """
    Insert a persistent note. Returns note_id (UUID string).
    """
    if not isinstance(chat_id, int) or chat_id <= 0:
        raise ValueError("chat_id must be a positive int")

    text = (text or "").strip()
    if not text:
        raise ValueError("text must be non-empty")

    note_id = str(uuid.uuid4())

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO notes (id, chat_id, text)
            VALUES (%s::uuid, %s, %s);
            """,
            (note_id, chat_id, text),
        )

    return note_id


def create_task(chat_id: int, text: str) -> str:
    """
    Insert a persistent task (done=false). Returns task_id (UUID string).
    """
    if not isinstance(chat_id, int) or chat_id <= 0:
        raise ValueError("chat_id must be a positive int")

    text = (text or "").strip()
    if not text:
        raise ValueError("text must be non-empty")

    task_id = str(uuid.uuid4())

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO tasks (id, chat_id, text, done)
            VALUES (%s::uuid, %s, %s, FALSE);
            """,
            (task_id, chat_id, text),
        )

    return task_id


def list_open_tasks(chat_id: int, limit: int = 5) -> list[dict]:
    """
    List most-recent open tasks for a chat_id.
    """
    if not isinstance(chat_id, int) or chat_id <= 0:
        raise ValueError("chat_id must be a positive int")
    if not isinstance(limit, int) or limit <= 0:
        limit = 5

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id::text, text, done, created_at
            FROM tasks
            WHERE chat_id = %s AND done = FALSE
            ORDER BY created_at DESC
            LIMIT %s;
            """,
            (chat_id, limit),
        ).fetchall()

    return [{"id": r[0], "text": r[1], "done": bool(r[2]), "created_at": r[3].isoformat()} for r in rows]


def mark_task_done(chat_id: int, task_id: str) -> bool:
    """
    Mark a task done. Returns True if updated, False if not found/already done/invalid id.
    """
    if not isinstance(chat_id, int) or chat_id <= 0:
        raise ValueError("chat_id must be a positive int")

    task_id = (task_id or "").strip()
    if not task_id:
        raise ValueError("task_id must be non-empty")

    # Validate UUID to avoid DB exceptions like:
    # psycopg.errors.InvalidTextRepresentation: invalid input syntax for type uuid
    try:
        uuid.UUID(task_id)
    except Exception:
        return False

    with connect() as conn:
        cur = conn.execute(
            """
            UPDATE tasks
            SET done = TRUE,
                done_at = NOW(),
                updated_at = NOW()
            WHERE chat_id = %s
              AND id = %s::uuid
              AND done = FALSE;
            """,
            (chat_id, task_id),
        )
        return bool(cur.rowcount and cur.rowcount > 0)



def search_notes_tasks(chat_id: int, query: str, limit: int = 10) -> list[dict]:
    """
    Simple keyword search across tasks + notes for a chat.
    Returns unified list sorted by created_at desc.
    """
    if not isinstance(chat_id, int) or chat_id <= 0:
        raise ValueError("chat_id must be a positive int")

    query = (query or "").strip()
    if not query:
        raise ValueError("query must be non-empty")

    if not isinstance(limit, int) or limit <= 0:
        limit = 10

    like = f"%{query}%"

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT kind, id, text, done, created_at
            FROM (
              SELECT 'task'::text AS kind, id::text AS id, text, done, created_at
              FROM tasks
              WHERE chat_id = %s AND text ILIKE %s

              UNION ALL

              SELECT 'note'::text AS kind, id::text AS id, text, NULL::boolean AS done, created_at
              FROM notes
              WHERE chat_id = %s AND text ILIKE %s
            ) x
            ORDER BY created_at DESC
            LIMIT %s;
            """,
            (chat_id, like, chat_id, like, limit),
        ).fetchall()

    out = []
    for kind, _id, text, done, created_at in rows:
        out.append(
            {
                "kind": kind,
                "id": _id,
                "text": text,
                "done": None if done is None else bool(done),
                "created_at": created_at.isoformat(),
            }
        )
    return out



def get_setting(key: str) -> str | None:
    """
    Returns the setting value for key, or None if missing.
    """
    key = key.strip()
    if not key:
        raise ValueError("key must be non-empty")

    with connect() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = %s;",
            (key,),
        ).fetchone()
    return row[0] if row else None


def set_setting(key: str, value: str) -> None:
    """
    Upserts a setting value (string).
    """
    key = key.strip()
    if not key:
        raise ValueError("key must be non-empty")

    if value is None:
        raise ValueError("value must not be None")

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (%s, %s)
            ON CONFLICT (key)
            DO UPDATE SET value = EXCLUDED.value, updated_at = NOW();
            """,
            (key, str(value)),
        )


def get_bool_setting(key: str, default: bool) -> bool:
    """
    Reads a boolean-ish setting.
    Accepted true values: 1, true, yes, y, on
    Accepted false values: 0, false, no, n, off
    Anything else => default
    """
    raw = get_setting(key)
    if raw is None:
        return default

    v = raw.strip().lower()
    if v in {"1", "true", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "no", "n", "off"}:
        return False
    return default




def canonicalize_label_key(name: str) -> str:
    """
    Normalizes a label name into a canonical key.
    Rules:
      - lowercase
      - trim
      - spaces and '-' become '_'
      - remove non-alphanumeric/underscore
      - collapse multiple underscores
    Examples:
      "To Do" -> "to_do"
      "Work-Admin" -> "work_admin"
      "  Personal!!! " -> "personal"
    """
    if name is None:
        raise ValueError("name must not be None")

    s = name.strip().lower()
    if not s:
        raise ValueError("name must be non-empty")

    s = s.replace("-", " ")
    s = re.sub(r"\s+", "_", s)            # spaces -> _
    s = re.sub(r"[^a-z0-9_]", "", s)      # drop junk
    s = re.sub(r"_+", "_", s)             # collapse __
    s = s.strip("_")
    if not s:
        raise ValueError("name becomes empty after canonicalization")
    return s


def upsert_label(name: str) -> str:
    """
    Upserts label by canonical key.
    Returns the canonical_key.

    - If same canonical_key exists, updates the display name to latest provided.
    - Ensures canonical_key uniqueness.
    """
    canonical_key = canonicalize_label_key(name)

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO labels (name, canonical_key)
            VALUES (%s, %s)
            ON CONFLICT (canonical_key)
            DO UPDATE SET name = EXCLUDED.name;
            """,
            (name.strip(), canonical_key),
        )
    return canonical_key


def list_labels() -> list[dict]:
    """
    Returns labels as list of dicts sorted by canonical_key:
      [{"name": "...", "canonical_key": "..."}, ...]
    """
    with connect() as conn:
        rows = conn.execute(
            "SELECT name, canonical_key FROM labels ORDER BY canonical_key ASC;"
        ).fetchall()

    return [{"name": r[0], "canonical_key": r[1]} for r in rows]

# db.py (add below labels functions)

def save_message_map(chat_id: int, message_id: int, notion_page_id: str) -> None:
    """
    Stores mapping from (chat_id, message_id) -> notion_page_id.
    Idempotent: updates notion_page_id if mapping exists.
    """
    if chat_id is None or message_id is None:
        raise ValueError("chat_id and message_id must not be None")
    if not isinstance(chat_id, int) or not isinstance(message_id, int):
        raise TypeError("chat_id and message_id must be int")
    if chat_id <= 0 or message_id <= 0:
        raise ValueError("chat_id and message_id must be positive")

    notion_page_id = (notion_page_id or "").strip()
    if not notion_page_id:
        raise ValueError("notion_page_id must be non-empty")

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO telegram_message_map (chat_id, message_id, notion_page_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (chat_id, message_id)
            DO UPDATE SET notion_page_id = EXCLUDED.notion_page_id;
            """,
            (chat_id, message_id, notion_page_id),
        )


def get_notion_page_id(chat_id: int, message_id: int) -> str | None:
    """
    Fetches notion_page_id for a Telegram message, else None.
    """
    if chat_id is None or message_id is None:
        raise ValueError("chat_id and message_id must not be None")
    if not isinstance(chat_id, int) or not isinstance(message_id, int):
        raise TypeError("chat_id and message_id must be int")

    with connect() as conn:
        row = conn.execute(
            """
            SELECT notion_page_id
            FROM telegram_message_map
            WHERE chat_id = %s AND message_id = %s;
            """,
            (chat_id, message_id),
        ).fetchone()

    return row[0] if row else None




def enqueue_job(job_type: str, payload: dict[str, Any], run_after: datetime | None = None) -> str:
    """
    Adds a job to the queue (status=queued). Returns job_id (UUID string).
    """
    job_type = (job_type or "").strip()
    if not job_type:
        raise ValueError("job_type must be non-empty")
    if payload is None or not isinstance(payload, dict):
        raise TypeError("payload must be a dict")

    job_id = str(uuid.uuid4())
    if run_after is None:
        run_after = datetime.now(timezone.utc)

    # Ensure timezone-aware
    if run_after.tzinfo is None:
        run_after = run_after.replace(tzinfo=timezone.utc)

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO job_queue (id, type, payload, status, run_after)
            VALUES (%s::uuid, %s, %s, 'queued', %s);
            """,
            (job_id, job_type, Jsonb(payload), run_after),
        )
    return job_id



def claim_next_job(types: Iterable[str] | None = None) -> dict | None:
    """
    Atomically claims the next due queued job and marks it as running.
    Uses FOR UPDATE SKIP LOCKED for safe concurrent workers.
    Returns a dict with job fields or None if none available.
    """
    type_list = None
    if types is not None:
        type_list = [t.strip() for t in types if (t or "").strip()]
        if not type_list:
            type_list = None

    with connect() as conn:
        # Do selection + update in a single transaction.
        conn.autocommit = False
        try:
            now = datetime.now(timezone.utc)

            if type_list is None:
                row = conn.execute(
                    """
                    SELECT id, type, payload, retry_count
                    FROM job_queue
                    WHERE status = 'queued'
                      AND run_after <= %s
                    ORDER BY run_after ASC, created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1;
                    """,
                    (now,),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT id, type, payload, retry_count
                    FROM job_queue
                    WHERE status = 'queued'
                      AND run_after <= %s
                      AND type = ANY(%s)
                    ORDER BY run_after ASC, created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1;
                    """,
                    (now, type_list),
                ).fetchone()

            if not row:
                conn.rollback()
                return None

            job_id, job_type, payload, retry_count = row

            conn.execute(
                """
                UPDATE job_queue
                SET status = 'running',
                    locked_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s;
                """,
                (job_id,),
            )

            conn.commit()
            return {
                "id": str(job_id),
                "type": job_type,
                "payload": payload,
                "retry_count": retry_count,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.autocommit = True


def mark_job_done(job_id: str) -> None:
    """
    Marks a job as done.
    """
    job_id = (job_id or "").strip()
    if not job_id:
        raise ValueError("job_id must be non-empty")

    with connect() as conn:
        conn.execute(
            """
            UPDATE job_queue
            SET status = 'done',
                updated_at = NOW()
            WHERE id = %s::uuid;
            """,
            (job_id,),
        )


def mark_job_failed(job_id: str, error: str, backoff_seconds: int = 60) -> None:
    """
    Re-queues a job with backoff and increments retry_count.
    """
    job_id = (job_id or "").strip()
    if not job_id:
        raise ValueError("job_id must be non-empty")

    error = (error or "").strip() or "unknown error"
    if backoff_seconds < 0:
        backoff_seconds = 0

    from datetime import datetime, timezone, timedelta

    run_after = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)

    with connect() as conn:
        conn.execute(
            """
            UPDATE job_queue
            SET status = 'queued',
                retry_count = retry_count + 1,
                last_error = %s,
                run_after = %s,
                updated_at = NOW()
            WHERE id = %s::uuid;
            """,
            (error, run_after, job_id),
        )



# db.py (add below job queue functions)

from typing import Sequence


def upsert_embedding_chunk(
    kind: str,
    notion_page_id: str,
    chunk_index: int,
    content_hash: str,
    embedding: Sequence[float] | None,
) -> None:
    """
    Stores an embedding chunk, deduped by (kind, notion_page_id, chunk_index, content_hash).
    If the same unique key exists, updates embedding.
    """
    kind = (kind or "").strip().lower()
    if kind not in {"note", "task"}:
        raise ValueError("kind must be 'note' or 'task'")

    notion_page_id = (notion_page_id or "").strip()
    if not notion_page_id:
        raise ValueError("notion_page_id must be non-empty")

    if not isinstance(chunk_index, int) or chunk_index < 0:
        raise ValueError("chunk_index must be int >= 0")

    content_hash = (content_hash or "").strip()
    if not content_hash:
        raise ValueError("content_hash must be non-empty")

    emb_value = None
    if embedding is not None:
        lst = [float(x) for x in embedding]
        if not lst:
            raise ValueError("embedding must be non-empty if provided")
        emb_value = Vector(lst)  # <-- critical: sends correct pgvector type

    with connect() as conn:
        conn.execute(
            """
            INSERT INTO embedding_chunks (kind, notion_page_id, chunk_index, content_hash, embedding)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (kind, notion_page_id, chunk_index, content_hash)
            DO UPDATE SET embedding = EXCLUDED.embedding;
            """,
            (kind, notion_page_id, chunk_index, content_hash, emb_value),
        )

def search_similar(
    kind: str,
    query_embedding: Sequence[float],
    top_k: int = 5,
) -> list[dict]:
    """
    Returns top_k closest chunks by L2 distance (<->).
    Only returns rows where embedding IS NOT NULL.
    """
    kind = (kind or "").strip().lower()
    if kind not in {"note", "task"}:
        raise ValueError("kind must be 'note' or 'task'")

    if query_embedding is None:
        raise ValueError("query_embedding must not be None")

    q_list = [float(x) for x in query_embedding]
    if not q_list:
        raise ValueError("query_embedding must be non-empty")

    if top_k <= 0:
        top_k = 5

    qv = Vector(q_list)  # <-- critical: sends correct pgvector type

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT notion_page_id, chunk_index, content_hash, (embedding <-> %s) AS distance
            FROM embedding_chunks
            WHERE kind = %s
              AND embedding IS NOT NULL
            ORDER BY embedding <-> %s
            LIMIT %s;
            """,
            (qv, kind, qv, top_k),
        ).fetchall()

    return [
        {
            "notion_page_id": r[0],
            "chunk_index": r[1],
            "content_hash": r[2],
            "distance": float(r[3]),
        }
        for r in rows
    ]
