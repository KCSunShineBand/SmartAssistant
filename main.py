# main.py
from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

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
      - {"type": "message", "chat_id": int, "user_id": int|None, "text": str, "route": dict}
      - {"type": "callback", "chat_id": int, "user_id": int|None, "data": str, "callback": dict}
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
        user = msg.get("from") or {}
        text = (msg.get("text") or "").strip()

        return {
            "type": "message",
            "chat_id": chat.get("id"),
            "user_id": user.get("id"),
            "text": text,
            "route": route_text(text) if text else {"kind": "error", "error": "empty_text", "message": "empty message"},
        }

    if "callback_query" in update and isinstance(update["callback_query"], dict):
        cq = update["callback_query"]
        user = cq.get("from") or {}
        msg = cq.get("message") or {}
        chat = msg.get("chat") or {}
        data = (cq.get("data") or "").strip()

        # Parse callback only if present; otherwise return raw.
        cb = {"kind": "error", "error": "empty_callback", "message": "empty callback data"}
        if data:
            try:
                cb = parse_callback(data)
            except ValueError as e:
                cb = {"kind": "error", "error": "invalid_callback", "message": str(e), "data": data}

        return {
            "type": "callback",
            "chat_id": chat.get("id"),
            "user_id": user.get("id"),
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

    Behavior (MVP):
    - Normalize update
    - Run core handler
    - Execute reply actions via Telegram Bot API (sendMessage)
    - Return ack quickly (still includes actions for debug/testing)
    """
    try:
        update = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_json"})

    event = normalize_update(update)
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
            # Token not configured: dev mode -> don't count as an error
            pass
        except Exception:
            # Real send failure (network, 4xx/5xx, etc.)
            errors += 1

    return {"ok": True, "type": event.get("type"), "sent": sent, "errors": errors, "actions": actions}
