import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db import init_db, canonicalize_label_key, upsert_label, list_labels


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_canonicalize_label_key():
    assert canonicalize_label_key("To Do") == "to_do"
    assert canonicalize_label_key("Work-Admin") == "work_admin"
    assert canonicalize_label_key("  Personal!!! ") == "personal"


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_upsert_and_list_labels_dedup_by_canonical_key():
    init_db()

    k1 = upsert_label("To Do")
    assert k1 == "to_do"

    # same canonical key, different display name -> should update name, not create new
    k2 = upsert_label("To-Do")
    assert k2 == "to_do"

    labels = list_labels()
    keys = [x["canonical_key"] for x in labels]
    assert "to_do" in keys

    # Only one row for to_do
    assert keys.count("to_do") == 1
