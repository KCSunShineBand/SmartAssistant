# core.py

from __future__ import annotations

import os

import db

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

    Persistence strategy:
    - If DATABASE_URL is set -> use Postgres via db.py (persistent across Cloud Run instances/revisions)
    - Else -> use in-memory state (local/dev)

    MVP actions supported:
    - /note <text>
    - /todo <text>
    - /today
    - /done <task_id>
    - /search <query>
    - plain text -> note
    """
    et = event.get("type")
    chat_id = event.get("chat_id")

    if et != "message" or not isinstance(chat_id, int):
        return []

    text = (event.get("text") or "").strip()
    route = event.get("route") or {"kind": "text", "text": text}

    def reply(msg: str) -> List[Dict[str, Any]]:
        return [{"type": "reply", "chat_id": chat_id, "text": msg}]

    # DB mode switch
    db_enabled = bool(os.getenv("DATABASE_URL", "").strip())

    # In-memory buckets (still used for dev mode)
    state.notes.setdefault(chat_id, [])
    state.tasks.setdefault(chat_id, [])

    if route.get("kind") == "command":
        cmd = route.get("command")

        if cmd == "note":
            note_text = (route.get("text") or "").strip()
            if not note_text:
                return reply("Missing text. Usage: /note <text>")

            if db_enabled:
                db.init_db()
                nid = db.create_note(chat_id, note_text)
                return reply(f"Saved note: {nid}")
            else:
                nid = _next_id(state, "note")
                state.notes[chat_id].append(Note(id=nid, text=note_text, created_at=_now_iso()))
                return reply(f"Saved note: {nid}")

        if cmd == "todo":
            task_text = (route.get("text") or "").strip()
            if not task_text:
                return reply("Missing text. Usage: /todo <text>")

            if db_enabled:
                db.init_db()
                tid = db.create_task(chat_id, task_text)
                return reply(f"Added task: {tid}")
            else:
                tid = _next_id(state, "task")
                state.tasks[chat_id].append(Task(id=tid, text=task_text, created_at=_now_iso()))
                return reply(f"Added task: {tid}")

        if cmd == "today":
            if db_enabled:
                db.init_db()
                open_tasks = db.list_open_tasks(chat_id, limit=5)
                if not open_tasks:
                    return reply("No open tasks. Go touch grass 🌱")
                preview = "\n".join([f"- {t['id']}: {t['text']}" for t in open_tasks])
                return reply(f"Open tasks: {len(open_tasks)}\n{preview}")
            else:
                open_tasks = [t for t in state.tasks[chat_id] if not t.done]
                if not open_tasks:
                    return reply("No open tasks. Go touch grass 🌱")
                preview = "\n".join([f"- {t.id}: {t.text}" for t in open_tasks[-5:]])
                return reply(f"Open tasks: {len(open_tasks)}\n{preview}")

        if cmd == "done":
            task_id = (route.get("task_id") or "").strip()
            if not task_id:
                return reply("Missing task id. Usage: /done <task_id>")

            if db_enabled:
                db.init_db()
                ok = db.mark_task_done(chat_id, task_id)
                if ok:
                    return reply(f"Marked done: {task_id}")
                return reply(f"Task not found (or already done): {task_id}")
            else:
                for t in state.tasks[chat_id]:
                    if t.id == task_id:
                        if t.done:
                            return reply(f"{task_id} is already done.")
                        t.done = True
                        return reply(f"Marked done: {task_id}")
                return reply(f"Task not found: {task_id}")

        if cmd == "search":
            q = (route.get("query") or "").strip()
            if not q:
                return reply("Missing query. Usage: /search <query>")

            if db_enabled:
                db.init_db()
                hits = db.search_notes_tasks(chat_id, q, limit=10)
                if not hits:
                    return reply(f'No results for: "{q}"')

                lines = [f'Results for: "{q}"']
                # Keep it compact
                for h in hits[:10]:
                    if h["kind"] == "task":
                        status = "✅" if h.get("done") else "☐"
                        lines.append(f"- {status} {h['id']}: {h['text']}")
                    else:
                        snippet = (h["text"] or "").strip().replace("\n", " ")
                        if len(snippet) > 80:
                            snippet = snippet[:77] + "..."
                        lines.append(f"- 📝 {h['id']}: {snippet}")
                return reply("\n".join(lines))

            # dev/in-memory search
            ql = q.lower()
            task_hits = []
            for t in state.tasks[chat_id]:
                if ql in (t.text or "").lower():
                    status = "✅" if t.done else "☐"
                    task_hits.append(f"{status} {t.id}: {t.text}")

            note_hits = []
            for n in state.notes[chat_id]:
                if ql in (n.text or "").lower():
                    snippet = n.text.strip().replace("\n", " ")
                    if len(snippet) > 80:
                        snippet = snippet[:77] + "..."
                    note_hits.append(f"📝 {n.id}: {snippet}")

            if not task_hits and not note_hits:
                return reply(f'No results for: "{q}"')

            lines = [f'Results for: "{q}"']
            if task_hits:
                lines.append("Tasks:")
                lines.extend([f"- {x}" for x in task_hits[:5]])
            if note_hits:
                lines.append("Notes:")
                lines.extend([f"- {x}" for x in note_hits[:5]])
            return reply("\n".join(lines))

        if cmd == "help":
            return reply(
                "Commands:\n"
                "/note <text>\n"
                "/todo <text>\n"
                "/today\n"
                "/done <task_id>\n"
                "/search <query>"
            )

        return reply(f"Command not implemented yet: /{cmd}")

    # Plain text path: treat as a note capture
    if route.get("kind") == "text":
        note_text = (route.get("text") or "").strip()
        if not note_text:
            return reply("Empty message")

        if db_enabled:
            db.init_db()
            nid = db.create_note(chat_id, note_text)
            return reply(f"Saved note: {nid}")
        else:
            nid = _next_id(state, "note")
            state.notes[chat_id].append(Note(id=nid, text=note_text, created_at=_now_iso()))
            return reply(f"Saved note: {nid}")

    if route.get("kind") == "unknown_command":
        return reply(f"Unknown command: /{route.get('command')} (try /help)")

    if route.get("kind") == "error":
        return reply(route.get("message", "Error"))

    return []
