import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import init_db, enqueue_job, claim_next_job, mark_job_done, mark_job_failed


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_enqueue_and_claim_and_done():
    init_db()

    job_id = enqueue_job("sync", {"x": 1})
    assert isinstance(job_id, str)

    job = claim_next_job(types=["sync"])
    assert job is not None
    assert job["id"] == job_id
    assert job["type"] == "sync"
    assert job["payload"]["x"] == 1

    # next claim should be none (already running)
    assert claim_next_job(types=["sync"]) is None

    mark_job_done(job_id)
    # done job should not be claimable
    assert claim_next_job(types=["sync"]) is None


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_failed_requeues_with_backoff():
    init_db()

    job_id = enqueue_job("embed", {"note": "abc"})
    job = claim_next_job(types=["embed"])
    assert job is not None
    assert job["id"] == job_id
    assert job["retry_count"] == 0

    mark_job_failed(job_id, "boom", backoff_seconds=2)

    # Immediately claiming again should return none (due to backoff)
    assert claim_next_job(types=["embed"]) is None

    # Fast-forward by creating a job already due, ensure claim works
    due_id = enqueue_job("embed", {"note": "due"}, run_after=datetime.now(timezone.utc) - timedelta(seconds=1))
    due_job = claim_next_job(types=["embed"])
    assert due_job is not None
    assert due_job["id"] == due_id
