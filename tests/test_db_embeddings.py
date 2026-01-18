import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import init_db, upsert_embedding_chunk, search_similar


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_upsert_and_search_similar_orders_by_distance():
    init_db()

    # Simple 3D vectors for deterministic distances
    upsert_embedding_chunk("note", "pageA", 0, "h1", [0.0, 0.0, 0.0])
    upsert_embedding_chunk("note", "pageB", 0, "h2", [1.0, 0.0, 0.0])
    upsert_embedding_chunk("note", "pageC", 0, "h3", [10.0, 0.0, 0.0])

    res = search_similar("note", [0.2, 0.0, 0.0], top_k=3)
    assert [r["notion_page_id"] for r in res] == ["pageA", "pageB", "pageC"]
    assert res[0]["distance"] <= res[1]["distance"] <= res[2]["distance"]


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_upsert_updates_embedding_for_same_unique_key():
    init_db()

    upsert_embedding_chunk("task", "pageT", 0, "hashX", [0.0, 0.0, 0.0])
    upsert_embedding_chunk("task", "pageT", 0, "hashX", [5.0, 0.0, 0.0])

    res = search_similar("task", [4.9, 0.0, 0.0], top_k=1)
    assert res[0]["notion_page_id"] == "pageT"
