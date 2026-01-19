# main.py
from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from fastapi import Body, Header, HTTPException
from typing import Optional

import db
import notion

from ui import parse_callback, route_text
from core import AppState, handle_event

import os
import requests

app = FastAPI(title="Smart Assistant Bot (MVP)")

STATE = AppState()

def _tg_api_url(method: str) -> str:
    """
    Build Telegram Bot API URL.

    Dev-safety:
    - If TELEGRAM_BOT_TOKEN is missing or looks like a placeholder, we raise RuntimeError.
      Webhook handler will catch and *skip sending* cleanly.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

    # common placeholders / accidental values
    bad_tokens = {
        "",
        "PUT_YOUR_REAL_BOT_TOKEN_HERE",
        "YOUR_BOT_TOKEN_HERE",
        "REPLACE_ME",
    }
    if token in bad_tokens or token.lower().startswith("put_your_"):
        raise RuntimeError("Telegram token not configured")

    return f"https://api.telegram.org/bot{token}/{method}"



def send_telegram_message(chat_id: int, text: str) -> dict:
    if not isinstance(chat_id, int):
        raise ValueError("chat_id must be int")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")

    url = _tg_api_url("sendMessage")
    payload = {"chat_id": chat_id, "text": text}
    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


def normalize_update(update: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize Telegram Update payload into a stable internal event shape.

    Returns a dict:
      - {"type": "message", "chat_id": int|None, "user_id": int|None, "message_id": int|None, "text": str, "route": dict}
      - {"type": "callback", "chat_id": int|None, "user_id": int|None, "data": str, "callback": dict}
      - {"type": "unsupported", "raw_keys": [...]}

    Notes:
    - Pure function: no network, no DB.
    - Safe: if Telegram adds fields, we won't crash.
    """
    if not isinstance(update, dict):
        return {"type": "unsupported", "raw_keys": []}

    if "message" in update and isinstance(update["message"], dict):
        msg = update["message"]
        chat = msg.get("chat") or {}
        frm = msg.get("from") or {}
        text = (msg.get("text") or "").strip()

        chat_id = chat.get("id")
        user_id = frm.get("id")
        message_id = msg.get("message_id")

        return {
            "type": "message",
            "chat_id": int(chat_id) if chat_id is not None else None,
            "user_id": int(user_id) if user_id is not None else None,
            "message_id": int(message_id) if message_id is not None else None,
            "text": text,
            "route": route_text(text)
            if text
            else {"kind": "error", "error": "empty_text", "message": "empty message"},
        }

    if "callback_query" in update and isinstance(update["callback_query"], dict):
        cq = update["callback_query"]
        frm = cq.get("from") or {}
        msg = cq.get("message") or {}
        chat = msg.get("chat") or {}
        data = (cq.get("data") or "").strip()

        cb = {"kind": "error", "error": "empty_callback", "message": "empty callback data"}
        if data:
            try:
                cb = parse_callback(data)
            except ValueError as e:
                cb = {"kind": "error", "error": "invalid_callback", "message": str(e), "data": data}

        chat_id = chat.get("id")
        user_id = frm.get("id")

        return {
            "type": "callback",
            "chat_id": int(chat_id) if chat_id is not None else None,
            "user_id": int(user_id) if user_id is not None else None,
            "data": data,
            "callback": cb,
        }

    return {"type": "unsupported", "raw_keys": sorted(list(update.keys()))}


@app.get("/health")
def health() -> Dict[str, bool]:
    return {"ok": True}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """
    Telegram webhook endpoint.

    Compatibility:
    - Returns response fields used by existing unit tests:
        { ok, type, sent, errors, actions }

    Owner-only gate:
    - If TELEGRAM_ALLOWED_USER_ID is set -> only that user_id is processed.
    - If TELEGRAM_ALLOWED_USER_ID is missing/invalid:
        - default: allow all (dev friendly)
        - strict mode: ignore all (fail closed)

    Strict mode triggers if:
      - APP_ENV in {"prod","production"}
      - or TELEGRAM_STRICT_OWNER_ONLY in {"1","true","yes"}
    """
    try:
        update = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_json"})

    event = normalize_update(update)
    event_type = event.get("type", "unsupported")

    strict = os.getenv("APP_ENV", "").lower() in {"prod", "production"} or os.getenv(
        "TELEGRAM_STRICT_OWNER_ONLY", ""
    ).strip().lower() in {"1", "true", "yes"}

    allowed_raw = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip()

    allowed_user_id = None
    if allowed_raw:
        try:
            allowed_user_id = int(allowed_raw)
        except Exception:
            allowed_user_id = None

    # If strict mode and allowlist missing/invalid -> deny all (fail closed)
    if strict and allowed_user_id is None:
        return {
            "ok": True,
            "type": event_type,
            "unauthorized": True,
            "sent": 0,
            "errors": 0,
            "actions": [],
        }

    # If allowlist is configured -> enforce it
    if allowed_user_id is not None:
        sender_user_id = event.get("user_id")
        try:
            if int(sender_user_id) != allowed_user_id:
                return {
                    "ok": True,
                    "type": event_type,
                    "unauthorized": True,
                    "sent": 0,
                    "errors": 0,
                    "actions": [],
                }
        except Exception:
            return {
                "ok": True,
                "type": event_type,
                "unauthorized": True,
                "sent": 0,
                "errors": 0,
                "actions": [],
            }

    actions = handle_event(event, STATE)

    sent = 0
    errors = 0

    for a in actions:
        if a.get("type") != "reply":
            continue
        try:
            send_telegram_message(chat_id=int(a["chat_id"]), text=str(a["text"]))
            sent += 1
        except RuntimeError:
            # Missing token in dev/test should not be treated as an error
            pass
        except Exception:
            errors += 1

    return {"ok": True, "type": event_type, "sent": sent, "errors": errors, "actions": actions}


@app.post("/admin/notion/setup")
async def admin_notion_setup(
    payload: dict = Body(...),
    x_admin_key: Optional[str] = Header(default=None),
):
    """
    One-time endpoint per PRD v1.5:
    - Creates KC Notes / KC Tasks in Notion (next step will implement)
    - Stores notion_notes_db_id / notion_tasks_db_id in Postgres settings
    - Seeds default labels into Postgres labels table
    - Ensures daily_brief_time + timezone defaults exist
    Security:
    - If ADMIN_SETUP_KEY env var is set, require header X-Admin-Key to match.
    """
    required_key = os.getenv("ADMIN_SETUP_KEY")
    if required_key and x_admin_key != required_key:
        raise HTTPException(status_code=401, detail="Unauthorized")

    parent_page_id = (payload or {}).get("parent_page_id")
    if not isinstance(parent_page_id, str) or not parent_page_id.strip():
        raise HTTPException(status_code=400, detail="parent_page_id is required")

    # Ensure DB schema exists before storing settings/labels
    try:
        db.init_db()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB init failed: {e}")

    # Create Notion DBs (implemented next step)
    try:
        result = notion.setup_databases(parent_page_id.strip())
        notes_db_id = result["notes_db_id"]
        tasks_db_id = result["tasks_db_id"]
    except KeyError:
        raise HTTPException(status_code=500, detail="setup_databases returned invalid shape")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Notion setup failed: {e}")

    # Store required settings
    db.set_setting("notion_notes_db_id", notes_db_id)
    db.set_setting("notion_tasks_db_id", tasks_db_id)

    # Defaults per PRD
    db.set_setting("daily_brief_time", db.get_setting("daily_brief_time", "07:30"))
    db.set_setting("timezone", db.get_setting("timezone", "Asia/Singapore"))

    # Seed default labels per PRD v1.5
    default_labels = [
        "Personal",
        "Finance",
        "Admin",
        "Projects",
        "LG Admin",
        "LG Client",
        "TDT Admin",
        "TDT Projects",
        "SAFEhaven",
    ]
    for name in default_labels:
        db.upsert_label(name)

    return {
        "ok": True,
        "notes_db_id": notes_db_id,
        "tasks_db_id": tasks_db_id,
        "seeded_labels": len(default_labels),
    }
