# core.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class Note:
    id: str
    text: str
    created_at: str  # ISO string
    labels: List[str] = field(default_factory=list)


@dataclass
class Task:
    id: str
    text: str
    created_at: str  # ISO string
    done: bool = False
    labels: List[str] = field(default_factory=list)


@dataclass
class AppState:
    """
    In-memory per-chat state.

    This is MVP scaffolding. Later we will persist to Notion and/or a DB.
    """
    notes: Dict[int, List[Note]] = field(default_factory=dict)  # chat_id -> notes
    tasks: Dict[int, List[Task]] = field(default_factory=dict)  # chat_id -> tasks
    seq: int = 0  # simple id counter


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _next_id(state: AppState, prefix: str) -> str:
    state.seq += 1
    return f"{prefix}_{state.seq}"


def handle_event(event: Dict[str, Any], state: AppState) -> List[Dict[str, Any]]:
    """
    Core app handler.

    Input:
      event: normalized event from main.normalize_update
      state: AppState (in-memory)

    Output:
      list of actions, e.g.
        [{"type": "reply", "chat_id": 123, "text": "..." }]

    MVP actions supported:
    - /note <text>  -> stores note
    - /todo <text>  -> stores task (not done)
    - /today        -> shows open tasks count + last few tasks
    - /done <id>    -> marks a task done
    - plain text    -> treated as note (per PRD "single chat only" quick capture style)
    """
    et = event.get("type")
    chat_id = event.get("chat_id")

    if et != "message" or not isinstance(chat_id, int):
        return []  # ignore callbacks for now; we'll wire them next

    text = (event.get("text") or "").strip()
    route = event.get("route") or {"kind": "text", "text": text}

    # Ensure buckets exist
    state.notes.setdefault(chat_id, [])
    state.tasks.setdefault(chat_id, [])

    # Helper to respond
    def reply(msg: str) -> List[Dict[str, Any]]:
        return [{"type": "reply", "chat_id": chat_id, "text": msg}]

    if route.get("kind") == "command":
        cmd = route.get("command")
        if cmd == "note":
            nid = _next_id(state, "note")
            state.notes[chat_id].append(Note(id=nid, text=route.get("text", ""), created_at=_now_iso()))
            return reply(f"Saved note: {nid}")

        if cmd == "todo":
            tid = _next_id(state, "task")
            state.tasks[chat_id].append(Task(id=tid, text=route.get("text", ""), created_at=_now_iso()))
            return reply(f"Added task: {tid}")

        if cmd == "today":
            open_tasks = [t for t in state.tasks[chat_id] if not t.done]
            if not open_tasks:
                return reply("No open tasks. Go touch grass 🌱")
            preview = "\n".join([f"- {t.id}: {t.text}" for t in open_tasks[-5:]])
            return reply(f"Open tasks: {len(open_tasks)}\n{preview}")

        if cmd == "done":
            task_id = route.get("task_id")
            if not task_id:
                return reply("Missing task id. Usage: /done <task_id>")
            for t in state.tasks[chat_id]:
                if t.id == task_id:
                    if t.done:
                        return reply(f"{task_id} is already done.")
                    t.done = True
                    return reply(f"Marked done: {task_id}")
            return reply(f"Task not found: {task_id}")

        if cmd == "help":
            return reply(
                "Commands:\n"
                "/note <text>\n"
                "/todo <text>\n"
                "/today\n"
                "/done <task_id>\n"
                "/search <query> (coming soon)"
            )

        # Known but not implemented yet
        return reply(f"Command not implemented yet: /{cmd}")

    # Plain text path: treat as a note capture
    if route.get("kind") == "text":
        nid = _next_id(state, "note")
        state.notes[chat_id].append(Note(id=nid, text=route.get("text", ""), created_at=_now_iso()))
        return reply(f"Saved note: {nid}")

    # Errors/unknown commands
    if route.get("kind") == "unknown_command":
        return reply(f"Unknown command: /{route.get('command')} (try /help)")

    if route.get("kind") == "error":
        return reply(route.get("message", "Error"))

    return []
