import os
import pytest
from fastapi.testclient import TestClient

import db
import main


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="DATABASE_URL not set")
def test_webhook_persists_telegram_chat_id(monkeypatch):
    db.init_db()

    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "111")
    monkeypatch.delenv("TELEGRAM_STRICT_OWNER_ONLY", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)

    client = TestClient(main.app)

    update = {
        "message": {
            "message_id": 1,
            "from": {"id": 111},
            "chat": {"id": 222},
            "text": "/help",
        }
    }

    r = client.post("/telegram/webhook", json=update)
    assert r.status_code == 200
    assert db.get_setting("telegram_chat_id") == "222"
