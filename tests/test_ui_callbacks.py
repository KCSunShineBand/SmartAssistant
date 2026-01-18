import pytest

from ui import (
    TELEGRAM_CALLBACK_MAX_BYTES,
    callback_len_bytes,
    encode_callback,
    parse_callback,
)


def test_encode_no_params():
    assert encode_callback("OPEN_NOTION") == "OPEN_NOTION"


def test_encode_and_parse_roundtrip():
    data = encode_callback("LABEL_TOGGLE", {"id": "abc123", "label": "LG Admin"})
    parsed = parse_callback(data)
    assert parsed["action"] == "LABEL_TOGGLE"
    assert parsed["params"]["id"] == "abc123"
    assert parsed["params"]["label"] == "LG Admin"


def test_parse_ignores_garbage_segments():
    parsed = parse_callback("ACTION|ok=1|GARBAGE|also=2")
    assert parsed["action"] == "ACTION"
    assert parsed["params"] == {"ok": "1", "also": "2"}


def test_encode_rejects_bad_action():
    with pytest.raises(ValueError):
        encode_callback("")
    with pytest.raises(ValueError):
        encode_callback("A|B")


def test_encode_rejects_bad_keys():
    with pytest.raises(ValueError):
        encode_callback("ACTION", {"": "x"})
    with pytest.raises(ValueError):
        encode_callback("ACTION", {"a|b": "x"})
    with pytest.raises(ValueError):
        encode_callback("ACTION", {"a=b": "x"})


def test_parse_rejects_empty():
    with pytest.raises(ValueError):
        parse_callback("")
    with pytest.raises(ValueError):
        parse_callback("   ")


def test_callback_length_helper():
    data = encode_callback("A", {"k": "v"})
    assert callback_len_bytes(data) <= TELEGRAM_CALLBACK_MAX_BYTES


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
