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
from core import handle_event, build_daily_brief_text


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


def send_telegram_message(
    chat_id: int,
    text: str,
    *,
    reply_markup: Dict[str, Any] = None,
    parse_mode: str = None,
    disable_web_page_preview: bool = None,
) -> dict:
    """
    Send a Telegram message.

    `reply_markup` supports inline keyboards (buttons).
    """
    if not isinstance(chat_id, int):
        raise ValueError("chat_id must be int")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a non-empty string")

    url = _tg_api_url("sendMessage")
    payload: Dict[str, Any] = {"chat_id": chat_id, "text": text}

    if reply_markup is not None:
        if not isinstance(reply_markup, dict):
            raise ValueError("reply_markup must be a dict when provided")
        payload["reply_markup"] = reply_markup

    if parse_mode:
        payload["parse_mode"] = parse_mode

    if disable_web_page_preview is not None:
        payload["disable_web_page_preview"] = bool(disable_web_page_preview)

    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    return r.json()

def edit_telegram_message(
    chat_id: int,
    message_id: int,
    text: str,
    *,
    reply_markup: Dict[str, Any] = None,
    parse_mode: str = None,
    disable_web_page_preview: bool = None,
) -> dict:
    """
    Edit an existing Telegram message (typically after a callback).
    """
    if not isinstance(chat_id, int):
        raise ValueError("chat_id must be int")
    if not isinstance(message_id, int):
        raise ValueError("message_id must be int")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be non-empty string")

    url = _tg_api_url("editMessageText")
    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
    }

    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    if parse_mode is not None:
        payload["parse_mode"] = parse_mode

    if disable_web_page_preview is not None:
        payload["disable_web_page_preview"] = bool(disable_web_page_preview)

    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


def answer_callback_query(
    callback_id: str,
    *,
    text: str | None = None,
    show_alert: bool = False,
) -> dict:
    """
    Acknowledge a Telegram callback so the client stops showing the loading spinner.

    Telegram method: answerCallbackQuery
    """
    if not isinstance(callback_id, str) or not callback_id.strip():
        raise ValueError("callback_id must be a non-empty string")

    url = _tg_api_url("answerCallbackQuery")
    payload: Dict[str, Any] = {"callback_query_id": callback_id.strip()}

    if text is not None:
        payload["text"] = str(text)

    if show_alert:
        payload["show_alert"] = True

    r = requests.post(url, json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


def normalize_update(update: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize Telegram Update payload into a stable internal event shape.

    Returns a dict:
      - {"type": "message", "chat_id": int|None, "user_id": int|None, "message_id": int|None, "text": str, "route": dict}
      - {"type": "callback", "chat_id": int|None, "user_id": int|None, "message_id": int|None,
         "callback_id": str|None, "data": str, "callback": dict}
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
        chat = (msg.get("chat") or {}) if isinstance(msg, dict) else {}
        data = (cq.get("data") or "").strip()

        callback_id = cq.get("id")  # Telegram callback_query.id (string)
        message_id = msg.get("message_id") if isinstance(msg, dict) else None

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
            "message_id": int(message_id) if message_id is not None else None,
            "callback_id": str(callback_id) if callback_id is not None else None,
            "data": data,
            "callback": cb,
        }

    return {"type": "unsupported", "raw_keys": sorted(list(update.keys()))}



@app.get("/health")
def health() -> Dict[str, bool]:
    return {"ok": True}

@app.get("/debug/env")
def debug_env(x_admin_key: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """
    Debug helper: returns ONLY environment variable NAMES (never values).

    Security:
    - Requires X-Admin-Key header.
    - Key comes from ADMIN_DEBUG_KEY, or falls back to ADMIN_SETUP_KEY.
    - If no key is configured, endpoint returns 404 (acts like it doesn't exist).
    """
    required_key = (os.getenv("ADMIN_DEBUG_KEY") or os.getenv("ADMIN_SETUP_KEY") or "").strip()

    if not required_key:
        # Hide endpoint entirely if not configured
        raise HTTPException(status_code=404, detail="Not found")

    if (x_admin_key or "").strip() != required_key:
        raise HTTPException(status_code=401, detail="Unauthorized")

    names = sorted(os.environ.keys())
    return {"ok": True, "count": len(names), "names": names}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request):
    """
    Telegram webhook endpoint.

    Compatibility:
    - Returns response fields used by existing unit tests:
        { ok, type, sent, errors, actions }

    Webhook origin hardening (recommended):
    - If TELEGRAM_WEBHOOK_SECRET is set, require header:
        X-Telegram-Bot-Api-Secret-Token == TELEGRAM_WEBHOOK_SECRET
      (This header is sent by Telegram when you setWebhook with secret_token.)

    Owner-only gate:
    - If TELEGRAM_ALLOWED_USER_ID is set -> only that user_id is processed.
    - If TELEGRAM_ALLOWED_USER_ID is missing/invalid:
        - default: allow all (dev friendly)
        - strict mode: ignore all (fail closed)

    Strict mode triggers if:
      - APP_ENV in {"prod","production"}
      - or TELEGRAM_STRICT_OWNER_ONLY in {"1","true","yes"}
    """

    # --- optional Telegram webhook secret header check (cheap, before reading body) ---
    expected_hook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if expected_hook_secret:
        got = (request.headers.get("X-Telegram-Bot-Api-Secret-Token") or "").strip()
        if got != expected_hook_secret:
            # Return 200 so Telegram/clients don't aggressively retry; we just do nothing.
            return {
                "ok": True,
                "type": "unauthorized",
                "unauthorized": True,
                "sent": 0,
                "errors": 0,
                "actions": [],
            }

    try:
        update = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_json"})

    event = normalize_update(update)
    event_type = event.get("type", "unsupported")

    # --- ACK callback early to stop Telegram spinner (best-effort) ---
    if event_type == "callback":
        cbid = event.get("callback_id")
        if isinstance(cbid, str) and cbid.strip():
            try:
                answer_callback_query(cbid)
            except RuntimeError:
                # Missing token in dev/test -> ignore
                pass
            except Exception:
                # Don't fail webhook for callback ack issues
                pass

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

    # persist chat_id best-effort
    if os.getenv("DATABASE_URL", "").strip():
        try:
            db.init_db()
            cid = event.get("chat_id")
            if isinstance(cid, int):
                db.set_setting("telegram_chat_id", str(cid))
            if allowed_user_id is not None:
                db.set_setting("telegram_allowed_user_id", str(allowed_user_id))
        except Exception:
            pass

    actions = handle_event(event, STATE)

    sent = 0
    errors = 0

    for a in actions:
            # --- NEW: execute edit actions (e.g., after callback "done") ---
        if a.get("type") == "edit":
            try:
                chat_id = int(a["chat_id"])
                message_id = int(a["message_id"])
                remove_task_id = str(a.get("remove_task_id") or "").strip()

                # Try to re-render the original task list message from cache
                cache = getattr(STATE, "render_cache", {}).get((chat_id, message_id))
                if cache and isinstance(cache, dict):
                    tasks = list(cache.get("tasks") or [])
                    list_kind = cache.get("list_kind") or "tasks"

                    # Remove the completed task
                    tasks = [t for t in tasks if str(t.get("id")) != remove_task_id]

                    if not tasks:
                        # All done — replace message and remove keyboard
                        new_text = "All done 🎉"
                        new_markup = None
                    else:
                        # Rebuild text + keyboard
                        if list_kind == "today":
                            header = f"Open tasks: {len(tasks)}"
                            lines = []
                            keyboard_rows = []
                            for t in tasks:
                                tid = str(t.get("id") or "")
                                title = (t.get("title") or "").strip()
                                due = t.get("due")
                                due_txt = f" (due {due})" if due else ""
                                lines.append(f"- {tid}: {title}{due_txt}")
                                keyboard_rows.append(
                                    [
                                        {"text": "✅ Done", "callback_data": f"done|task_id={tid}"},
                                        {"text": "Open", "url": notion.page_url(tid)},
                                    ]
                                )
                            new_text = header + "\n" + "\n".join(lines)
                            new_markup = {"inline_keyboard": keyboard_rows}

                        elif list_kind == "inbox":
                            header = "Inbox (open tasks):"
                            lines = []
                            keyboard_rows = []
                            for t in tasks:
                                tid = str(t.get("id") or "")
                                title = (t.get("title") or "").strip()
                                due = t.get("due")
                                status = t.get("status") or "todo"
                                due_txt = f" (due {due})" if due else ""
                                lines.append(f"- [{status}] {tid}: {title}{due_txt}")
                                keyboard_rows.append(
                                    [
                                        {"text": "✅ Done", "callback_data": f"done|task_id={tid}"},
                                        {"text": "Open", "url": notion.page_url(tid)},
                                    ]
                                )
                            new_text = header + "\n" + "\n".join(lines)
                            new_markup = {"inline_keyboard": keyboard_rows}
                        else:
                            # Unknown kind — fallback to simple confirmation
                            new_text = f"✅ Done: {remove_task_id}"
                            new_markup = None

                    # Persist updated cache (or clear if empty)
                    try:
                        if hasattr(STATE, "render_cache"):
                            if tasks:
                                STATE.render_cache[(chat_id, message_id)] = {
                                    "list_kind": list_kind,
                                    "tasks": tasks,
                                    "text": new_text,
                                }
                            else:
                                STATE.render_cache.pop((chat_id, message_id), None)
                    except Exception:
                        pass

                    edit_telegram_message(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=new_text,
                        reply_markup=new_markup,
                        disable_web_page_preview=True,
                    )
                else:
                    # No cache — fallback to simple confirmation
                    edit_telegram_message(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=f"✅ Done: {remove_task_id}",
                        reply_markup=None,
                        disable_web_page_preview=True,
                    )

            except RuntimeError:
                # Missing token in dev/test should not be treated as an error
                pass
            except Exception:
                errors += 1
            continue

        # existing reply path
        if a.get("type") != "reply":
            continue

        chat_id = int(a["chat_id"])
        text = str(a["text"])

        # Only pass optional kwargs when they exist (avoid breaking old fakes/tests)
        kwargs = {}
        if a.get("reply_markup") is not None:
            kwargs["reply_markup"] = a.get("reply_markup")
        if a.get("parse_mode") is not None:
            kwargs["parse_mode"] = a.get("parse_mode")
        if a.get("disable_web_page_preview") is not None:
            kwargs["disable_web_page_preview"] = a.get("disable_web_page_preview")

        try:
            try:
                # Newer sender supports kwargs
                resp = send_telegram_message(chat_id, text, **kwargs)
            except TypeError:
                # Backwards-compatible: monkeypatched send_telegram_message(chat_id, text) in tests
                resp = send_telegram_message(chat_id, text)

            sent += 1

            # --- NEW: store task-list render cache if core emitted it ---
            # Look for a cache_task_list action for this chat_id in this same webhook run.
            try:
                result = (resp or {}).get("result") or {}
                mid = result.get("message_id")
                if isinstance(mid, int) and hasattr(STATE, "render_cache"):
                    for ca in actions:
                        if ca.get("type") == "cache_task_list" and int(ca.get("chat_id")) == chat_id:
                            STATE.render_cache[(chat_id, mid)] = {
                                "list_kind": ca.get("list_kind"),
                                "tasks": ca.get("tasks") or [],
                                "text": ca.get("text") or "",
                            }
                            break
            except Exception:
                # Never break webhook on cache issues
                pass

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


@app.post("/cron/daily-brief")
async def cron_daily_brief(
    request: Request,
    x_cron_key: Optional[str] = Header(default=None),
):
    """
    Trigger Daily Brief send (intended for Cloud Scheduler).

    Cloud Scheduler often sends Content-Type: application/octet-stream even if you
    try to set application/json. So we parse the raw body ourselves and treat it
    as JSON when possible.

    Security:
      - If CRON_DAILY_BRIEF_KEY env var is set, require header X-Cron-Key to match.

    Target chat:
      - payload.chat_id (preferred override)
      - else TELEGRAM_CHAT_ID env var
      - else (if DATABASE_URL set) settings.telegram_chat_id from Postgres
    """
    import json as _json

    required_key = os.getenv("CRON_DAILY_BRIEF_KEY", "").strip()
    if required_key and x_cron_key != required_key:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Parse payload from raw request body (works regardless of Content-Type)
    payload: dict = {}
    try:
        raw = await request.body()
        if raw:
            try:
                payload_obj = _json.loads(raw.decode("utf-8"))
                if isinstance(payload_obj, dict):
                    payload = payload_obj
            except Exception:
                payload = {}
    except Exception:
        payload = {}

    chat_id = None

    # payload override
    if payload.get("chat_id") is not None:
        try:
            chat_id = int(payload.get("chat_id"))
        except Exception:
            raise HTTPException(status_code=400, detail="chat_id must be int")

    # env fallback
    if chat_id is None:
        env_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
        if env_chat:
            try:
                chat_id = int(env_chat)
            except Exception:
                raise HTTPException(status_code=500, detail="TELEGRAM_CHAT_ID is invalid")

    # DB fallback
    if chat_id is None and os.getenv("DATABASE_URL", "").strip():
        try:
            db.init_db()
            v = (db.get_setting("telegram_chat_id") or "").strip()
            if v:
                chat_id = int(v)
        except Exception:
            pass

    if chat_id is None:
        raise HTTPException(
            status_code=400,
            detail="chat_id missing (set TELEGRAM_CHAT_ID, talk to the bot once with DB enabled, or send {\"chat_id\": <int>})",
        )

    # Build and send Daily Brief text (PRD-style sections when Notion is enabled)
    text = build_daily_brief_text(chat_id, STATE)

    try:
        send_telegram_message(chat_id=int(chat_id), text=str(text))
        sent = 1
        errors = 0
    except RuntimeError:
        # Missing token in dev/test should not be treated as an error
        sent = 0
        errors = 0
    except Exception:
        sent = 0
        errors = 1

    actions = [{"type": "reply", "chat_id": chat_id, "text": text}]
    return {"ok": True, "sent": sent, "errors": errors, "actions": actions}