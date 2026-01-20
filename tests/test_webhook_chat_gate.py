import os
import pytest
from fastapi.testclient import TestClient

import main


client = TestClient(main.app)


def _update(chat_id: int, user_id: int, text: str = "/help"):
    return {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "from": {"id": user_id},
            "chat": {"id": chat_id},
            "text": text,
        },
    }


def test_webhook_allows_expected_chat_when_chat_id_set(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_ID", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("TELEGRAM_STRICT_OWNER_ONLY", raising=False)

    # Make test deterministic: never call real Telegram API
    def fake_send(chat_id: int, text: str):
        return None

    monkeypatch.setattr(main, "send_telegram_message", fake_send)

    r = client.post("/telegram/webhook", json=_update(chat_id=111, user_id=999, text="/help"))
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data.get("unauthorized") is None  # success responses don't include it
    assert data["errors"] == 0
    assert isinstance(data["actions"], list)
    assert len(data["actions"]) >= 1
    assert data["actions"][0]["type"] == "reply"


def test_webhook_allows_expected_chat_when_chat_id_set(monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "111")
    monkeypatch.delenv("TELEGRAM_ALLOWED_USER_ID", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("TELEGRAM_STRICT_OWNER_ONLY", raising=False)

    r = client.post("/telegram/webhook", json=_update(chat_id=111, user_id=999, text="/help"))
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data.get("unauthorized") is None  # success responses don't include it
    assert data["errors"] == 0
    assert isinstance(data["actions"], list)
    assert len(data["actions"]) >= 1
    assert data["actions"][0]["type"] == "reply"


def test_webhook_user_gate_still_works(monkeypatch):
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_ID", "12345")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("TELEGRAM_STRICT_OWNER_ONLY", raising=False)

    r = client.post("/telegram/webhook", json=_update(chat_id=111, user_id=999, text="/help"))
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data.get("unauthorized") is True
    assert data["actions"] == []
