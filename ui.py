# ui.py
from __future__ import annotations

from typing import Any, Dict, Optional
from urllib.parse import quote_plus, unquote_plus


# Telegram callback_data hard limit is 64 bytes.
# We won't hard-fail by default (to avoid breaking flows),
# but we provide a helper check so callers can enforce it if they want.
TELEGRAM_CALLBACK_MAX_BYTES = 64


def encode_callback(action: str, params: Optional[Dict[str, Any]] = None) -> str:
    """
    Encode callback data into the required format:
      ACTION|k1=v1|k2=v2

    Rules:
    - action must be non-empty and must not contain "|"
    - keys must not contain "|" or "="
    - values are stringified; None values are omitted
    - values are URL-encoded to keep payload parseable
    """
    if not isinstance(action, str) or not action.strip():
        raise ValueError("action must be a non-empty string")
    action = action.strip()
    if "|" in action:
        raise ValueError('action must not contain "|"')

    if not params:
        data = action
    else:
        parts = [action]
        for k, v in params.items():
            if v is None:
                continue
            if not isinstance(k, str) or not k.strip():
                raise ValueError("param keys must be non-empty strings")
            k = k.strip()
            if "|" in k or "=" in k:
                raise ValueError('param keys must not contain "|" or "="')

            # Keep values compact; Telegram callback_data is tiny.
            s = str(v)
            parts.append(f"{k}={quote_plus(s)}")
        data = "|".join(parts)

    return data


def parse_callback(data: str) -> Dict[str, Any]:
    """
    Parse callback data encoded as:
      ACTION|k1=v1|k2=v2

    Returns:
      {"action": <str>, "params": <dict[str,str]>}

    Behavior:
    - Unknown/extra segments without "=" are ignored (safe forward-compat).
    - Empty/invalid input raises ValueError.
    """
    if not isinstance(data, str) or not data.strip():
        raise ValueError("callback data must be a non-empty string")

    raw = data.strip()
    chunks = raw.split("|")
    action = chunks[0].strip()
    if not action:
        raise ValueError("callback action is missing")

    params: Dict[str, str] = {}
    for seg in chunks[1:]:
        seg = seg.strip()
        if not seg or "=" not in seg:
            continue
        k, v = seg.split("=", 1)
        k = k.strip()
        if not k:
            continue
        params[k] = unquote_plus(v)

    return {"action": action, "params": params}


def callback_len_bytes(data: str) -> int:
    """Return UTF-8 byte length (Telegram limit is bytes, not chars)."""
    return len(data.encode("utf-8"))


# --- Command router (Telegram-agnostic, pure function) ---

SUPPORTED_COMMANDS = {
    "note",
    "todo",
    "today",
    "done",
    "search",
    "inbox",
    "settings",
    # optional quality-of-life aliases (won't break MVP)
    "start",
    "help",
}


def route_text(text: str) -> dict:
    """
    Telegram-agnostic command router.

    Input:
      text: raw message text (may include newlines)

    Output (dict):
      - If plain text (not a /command):
          {"kind": "text", "text": "<original trimmed text>"}

      - If supported command:
          {"kind": "command", "command": "<name>", "args": "<rest>"}
        Plus command-specific parsed fields:
          /note <text>     -> {"text": "<text>"}
          /todo <text>     -> {"text": "<text>"}
          /search <query>  -> {"query": "<query>"}
          /done <task_id>  -> {"task_id": "<task_id>"}

      - If unknown command:
          {"kind": "unknown_command", "command": "<name>", "args": "<rest>"}

      - If error (empty input or missing required args):
          {"kind": "error", "error": "<code>", "message": "<human readable>"}

    Notes:
    - Handles Telegram-style "/cmd@BotUsername ..." by stripping "@BotUsername".
    - Pure function: no network, no DB, no globals beyond SUPPORTED_COMMANDS.
    """
    if not isinstance(text, str):
        return {"kind": "error", "error": "invalid_input", "message": "text must be a string"}

    raw = text.strip()
    if not raw:
        return {"kind": "error", "error": "empty_text", "message": "empty message"}

    if not raw.startswith("/"):
        return {"kind": "text", "text": raw}

    # Split: "/command rest of message"
    first, *rest = raw.split(None, 1)  # split on any whitespace incl newlines
    cmd_token = first[1:]  # remove leading "/"
    if not cmd_token:
        return {"kind": "error", "error": "missing_command", "message": "missing command"}

    # Strip @botname if present: /note@MyBot
    cmd_name = cmd_token.split("@", 1)[0].strip().lower()
    args = rest[0].strip() if rest else ""

    # Help/start aliases (optional)
    if cmd_name in {"start", "help"}:
        return {"kind": "command", "command": "help", "args": args}

    if cmd_name not in SUPPORTED_COMMANDS:
        return {"kind": "unknown_command", "command": cmd_name, "args": args}

    # Commands requiring args
    if cmd_name in {"note", "todo", "search", "done"} and not args:
        return {
            "kind": "error",
            "error": f"missing_args_{cmd_name}",
            "message": f"/{cmd_name} requires an argument",
        }

    out = {"kind": "command", "command": cmd_name, "args": args}

    # Command-specific parsing
    if cmd_name in {"note", "todo"}:
        out["text"] = args
    elif cmd_name == "search":
        out["query"] = args
    elif cmd_name == "done":
        out["task_id"] = args.split()[0]

    return out
