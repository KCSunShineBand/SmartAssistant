# core.py

from __future__ import annotations

import os
import notion
import db

from dataclasses import dataclass, field
from datetime import datetime, date
from zoneinfo import ZoneInfo

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


from typing import Tuple  # add near other imports if not present

@dataclass
class AppState:
    """
    In-memory per-chat state.

    This is MVP scaffolding. Later we will persist to Notion and/or a DB.
    """
    notes: Dict[int, List[Note]] = field(default_factory=dict)  # chat_id -> notes
    tasks: Dict[int, List[Task]] = field(default_factory=dict)  # chat_id -> tasks
    seq: int = 0  # simple id counter

    # key: (chat_id, message_id) -> rendered list payload for later edit
    render_cache: Dict[Tuple[int, int], Dict[str, Any]] = field(default_factory=dict)

    # chat_id -> pending interaction state for multi-step UX (Done/Edit via item number)
    pending: Dict[int, Dict[str, Any]] = field(default_factory=dict)


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _next_id(state: AppState, prefix: str) -> str:
    state.seq += 1
    return f"{prefix}_{state.seq}"

def build_daily_brief_text(
    chat_id: int,
    state: AppState,
    *,
    today: Optional[date] = None,
    limit_per_section: int = 5,
) -> str:
    """
    Build Daily Brief text.

    - Notion enabled: sections (Overdue / Due Today / Doing / No Due)
    - DB or in-memory fallback: Open tasks list only (no due/status metadata)

    `today` is injectable for deterministic tests.
    """
    if not isinstance(chat_id, int):
        raise ValueError("chat_id must be int")

    if today is None:
        today = datetime.now(ZoneInfo("Asia/Singapore")).date()

    # Existing DB mode switch
    db_enabled = bool(os.getenv("DATABASE_URL", "").strip())

    # ---- Notion mode switch ----
    notion_token = (os.getenv("NOTION_TOKEN") or "").strip()
    notes_db_id = (os.getenv("NOTION_NOTES_DB_ID") or "").strip()
    tasks_db_id = (os.getenv("NOTION_TASKS_DB_ID") or "").strip()

    if db_enabled and (not notes_db_id or not tasks_db_id):
        # Best-effort: load Notion IDs from Postgres settings
        try:
            db.init_db()
            if not notes_db_id:
                notes_db_id = (db.get_setting("notion_notes_db_id") or "").strip()
            if not tasks_db_id:
                tasks_db_id = (db.get_setting("notion_tasks_db_id") or "").strip()
        except Exception:
            pass

    notion_enabled = bool(notion_token and notes_db_id and tasks_db_id)

    def _parse_due(due_val: Any) -> Optional[date]:
        if due_val is None:
            return None
        s = str(due_val).strip()
        if not s:
            return None
        # tolerate "YYYY-MM-DD" or ISO datetime strings
        s = s.split("T")[0]
        try:
            return date.fromisoformat(s)
        except Exception:
            return None

    def _norm_status(v: Any) -> str:
        s = (str(v or "todo")).strip().lower()
        return s.replace("-", "_").replace(" ", "_")

    def _clean_title(v: Any) -> str:
        title = (str(v or "")).strip()
        if not title:
            return "(untitled)"
        # keep it one-liner
        title = title.replace("\r", " ").replace("\n", " ").strip()
        return title

    def _fmt_task_line(idx: int, t: Dict[str, Any]) -> str:
        title = _clean_title(t.get("title"))
        due_d = _parse_due(t.get("due"))
        due_txt = f" (due {due_d.isoformat()})" if due_d else ""
        return f"{idx}. {title}{due_txt}"

    def _section(title: str, items: List[Dict[str, Any]]) -> str:
        if not items:
            return f"{title}: 0"

        show = items[:limit_per_section]
        lines = [f"{title}: {len(items)}"]

        for i, t in enumerate(show, start=1):
            lines.append(_fmt_task_line(i, t))

        if len(items) > len(show):
            lines.append(f"... (+{len(items) - len(show)} more)")

        return "\n".join(lines)

    header = f"Daily Brief ({today.isoformat()} SGT)"

    # --- Notion mode: real sections ---
    if notion_enabled:
        tasks = notion.list_inbox_tasks(tasks_db_id, limit=50)  # open tasks with status/due
        if not tasks:
            return header + "\n\nNo open tasks. Go touch grass 🌱"

        overdue: List[Dict[str, Any]] = []
        due_today: List[Dict[str, Any]] = []
        doing: List[Dict[str, Any]] = []
        no_due: List[Dict[str, Any]] = []

        for t in tasks:
            st = _norm_status(t.get("status"))
            if st in {"done", "completed", "complete"}:
                continue

            d = _parse_due(t.get("due"))

            if st in {"doing", "in_progress", "inprogress"}:
                doing.append(t)
                continue

            if d is None:
                no_due.append(t)
            elif d < today:
                overdue.append(t)
            elif d == today:
                due_today.append(t)
            else:
                # future-dated tasks: treat as "no due" bucket for now (still open)
                no_due.append(t)

        parts = [
            header,
            "",
            _section("⏰ Overdue", overdue),
            "",
            _section("📌 Due Today", due_today),
            "",
            _section("🛠️ Doing", doing),
            "",
            _section("📥 No Due Date / Next Up", no_due),
        ]
        return "\n".join(parts).strip()

    # --- DB / in-memory fallback: open tasks only ---
    if db_enabled:
        try:
            db.init_db()
            open_tasks = db.list_open_tasks(chat_id, limit=20)
        except Exception:
            open_tasks = []

        if not open_tasks:
            return header + "\n\nNo open tasks. Go touch grass 🌱"

        lines = [header, "", f"Open tasks: {len(open_tasks)}"]

        show = open_tasks[:limit_per_section]
        for i, t in enumerate(show, start=1):
            txt = (t.get("text") or "").strip() or "(untitled)"
            txt = txt.replace("\r", " ").replace("\n", " ").strip()
            lines.append(f"{i}. {txt}")

        if len(open_tasks) > limit_per_section:
            lines.append(f"... (+{len(open_tasks) - limit_per_section} more)")

        lines.append("")
        lines.append("Tip: connect Notion to get Overdue/Due Today/Doing sections.")
        return "\n".join(lines).strip()

    # in-memory
    state.tasks.setdefault(chat_id, [])
    open_tasks = [t for t in state.tasks[chat_id] if not t.done]
    if not open_tasks:
        return header + "\n\nNo open tasks. Go touch grass 🌱"

    lines = [header, "", f"Open tasks: {len(open_tasks)}"]
    tail = open_tasks[-20:]
    show = tail[:limit_per_section]

    for i, t in enumerate(show, start=1):
        txt = (t.text or "").strip() or "(untitled)"
        txt = txt.replace("\r", " ").replace("\n", " ").strip()
        lines.append(f"{i}. {txt}")

    if len(tail) > limit_per_section:
        lines.append(f"... (+{len(tail) - limit_per_section} more)")

    lines.append("")
    lines.append("Tip: connect Notion to get Overdue/Due Today/Doing sections.")
    return "\n".join(lines).strip()



def handle_event(event: Dict[str, Any], state: AppState) -> List[Dict[str, Any]]:
    """
    Core app handler.

    Supports:
    - /note <text>
    - /todo <text>
    - /today
    - /inbox
    - /done <task_id>
    - /search <query>
    - /settings
    - /help
    - callback actions for task list UX:
        - pick_done (asks for item number, then marks done)
        - pick_edit (asks for item number, then asks for new text, then updates title)
    """
    et = event.get("type")
    chat_id = event.get("chat_id")

    if et not in {"message", "callback"} or not isinstance(chat_id, int):
        return []

    def reply(msg: str, **extra: Any) -> List[Dict[str, Any]]:
        d: Dict[str, Any] = {"type": "reply", "chat_id": chat_id, "text": msg}
        for k, v in (extra or {}).items():
            if v is not None:
                d[k] = v
        return [d]

    # Build route for message vs callback
    if et == "message":
        text = (event.get("text") or "").strip()
        route = event.get("route") or {"kind": "text", "text": text}
    else:
        cb = event.get("callback") or {}
        if cb.get("kind") == "error":
            return reply(cb.get("message") or "Invalid action")

        action = (cb.get("action") or "").strip()
        params = cb.get("params") or {}

        if action in {"today", "inbox", "help", "settings"}:
            route = {"kind": "command", "command": action}
        elif action == "done":
            task_id = (params.get("task_id") or params.get("id") or "").strip()
            route = {"kind": "command", "command": "done", "task_id": task_id}
        elif action in {"pick_done", "pick_edit"}:
            route = {"kind": "pick_action", "action": action}
        else:
            return reply(f"Unknown action: {action}")

    # Existing DB mode switch
    db_enabled = bool(os.getenv("DATABASE_URL", "").strip())

    # ---- Notion mode switch ----
    notion_token = (os.getenv("NOTION_TOKEN") or "").strip()
    notes_db_id = (os.getenv("NOTION_NOTES_DB_ID") or "").strip()
    tasks_db_id = (os.getenv("NOTION_TASKS_DB_ID") or "").strip()

    if db_enabled and (not notes_db_id or not tasks_db_id):
        # Best-effort: load Notion IDs from Postgres settings
        try:
            db.init_db()
            if not notes_db_id:
                notes_db_id = (db.get_setting("notion_notes_db_id") or "").strip()
            if not tasks_db_id:
                tasks_db_id = (db.get_setting("notion_tasks_db_id") or "").strip()
        except Exception:
            pass

    notion_enabled = bool(notion_token and notes_db_id and tasks_db_id)

    # In-memory buckets (dev fallback)
    state.notes.setdefault(chat_id, [])
    state.tasks.setdefault(chat_id, [])

    def _make_title(s: str, max_len: int = 80) -> str:
        s = (s or "").strip()
        if not s:
            return "Untitled"
        first = s.splitlines()[0].strip()
        if len(first) <= max_len:
            return first
        return first[: max_len - 3] + "..."

    def _open_in_notion_markup(page_id: str) -> Dict[str, Any]:
        url = notion.page_url(page_id)
        return {"inline_keyboard": [[{"text": "Open in Notion", "url": url}]]}

    def _two_button_task_list_markup() -> Dict[str, Any]:
        # Only 2 buttons as requested
        return {
            "inline_keyboard": [
                [
                    {"text": "Done", "callback_data": "pick_done"},
                    {"text": "Edit", "callback_data": "pick_edit"},
                ]
            ]
        }

    def _save_message_map(kind: str, notion_page_id: str) -> None:
        """
        Best-effort traceability: Telegram message -> Notion page.

        Supports multiple historical db.save_message_map signatures.
        Primary expected signature (per current unit tests):
        save_message_map(message_id, kind, notion_page_id, chat_id, user_id=None)
        """
        try:
            mid = event.get("message_id")
            uid = event.get("user_id")

            if (not db_enabled) or mid is None:
                return

            db.init_db()

            # 1) Current tests expect: (message_id, kind, notion_page_id, chat_id, user_id=None)
            try:
                db.save_message_map(int(mid), str(kind), str(notion_page_id), int(chat_id), uid)
                return
            except TypeError:
                pass

            # 2) Variant without user_id
            try:
                db.save_message_map(int(mid), str(kind), str(notion_page_id), int(chat_id))
                return
            except TypeError:
                pass

            # 3) Keyword-args variants (different parameter names)
            try:
                db.save_message_map(
                    message_id=int(mid),
                    kind=str(kind),
                    notion_page_id=str(notion_page_id),
                    chat_id=int(chat_id),
                    user_id=uid,
                )
                return
            except TypeError:
                pass

            # 4) Older minimal variants
            try:
                db.save_message_map(int(chat_id), int(mid), str(notion_page_id))
                return
            except TypeError:
                pass

        except Exception:
            return


    # --- NEW: Multi-step UX handling for Done/Edit via item number ---
    if et == "message":
        pending = state.pending.get(chat_id)

        # If user sends a command while pending, treat it as a reset (avoid accidental note capture).
        if pending and isinstance(text, str) and text.strip().startswith("/"):
            state.pending.pop(chat_id, None)
            # continue into normal routing

        # Only intercept plain text (non-command) when pending exists
        if pending and route.get("kind") == "text":
            mode = (pending.get("mode") or "").strip()
            source_mid = pending.get("source_message_id")
            raw = (text or "").strip()

            def _get_cached_tasks() -> List[Dict[str, Any]] | None:
                try:
                    smid = int(source_mid)
                except Exception:
                    return None
                cache = state.render_cache.get((chat_id, smid))
                if not cache or not isinstance(cache, dict):
                    return None
                tasks = cache.get("tasks") or []
                if not isinstance(tasks, list):
                    return None
                return tasks

            if mode in {"done_pick", "edit_pick"}:
                if not raw.isdigit():
                    return reply("Reply with the item number (e.g. 2).")

                idx = int(raw)
                tasks = _get_cached_tasks()
                if not tasks:
                    state.pending.pop(chat_id, None)
                    return reply("Task list expired. Run /today or /inbox again.")

                if idx < 1 or idx > len(tasks):
                    return reply(f"Invalid number. Choose 1 to {len(tasks)}.")

                task = tasks[idx - 1]
                task_id = str(task.get("id") or "").strip()
                if not task_id:
                    state.pending.pop(chat_id, None)
                    return reply("That item is missing an id. Run /today again.")

                if mode == "done_pick":
                    # perform done
                    if notion_enabled:
                        ok = notion.mark_task_done(task_id)
                        if not ok:
                            state.pending.pop(chat_id, None)
                            return reply("Could not mark done (Notion). Try /today again.")
                    elif db_enabled:
                        db.init_db()
                        ok = db.mark_task_done(chat_id, task_id)
                        if not ok:
                            state.pending.pop(chat_id, None)
                            return reply("Could not mark done. Try /today again.")
                    else:
                        for t in state.tasks[chat_id]:
                            if t.id == task_id:
                                t.done = True
                                break

                    state.pending.pop(chat_id, None)

                    # edit the original list message to remove item + re-render list
                    try:
                        smid = int(source_mid)
                    except Exception:
                        return reply("Done. (Could not update the list message.)")

                    return [{
                        "type": "edit",
                        "chat_id": chat_id,
                        "message_id": smid,
                        "remove_task_id": task_id,
                    }]

                # edit_pick -> ask for new text next
                state.pending[chat_id] = {
                    "mode": "edit_new_text",
                    "source_message_id": int(source_mid) if isinstance(source_mid, int) or str(source_mid).isdigit() else source_mid,
                    "task_id": task_id,
                    "item_number": idx,
                }
                return reply(f"Send the new text for item {idx}.")

            if mode == "edit_new_text":
                task_id = str(pending.get("task_id") or "").strip()
                item_no = pending.get("item_number")
                new_title = raw

                if not new_title:
                    return reply("New text cannot be empty. Send the updated task text.")

                # update title
                if notion_enabled:
                    notion.update_task_title(task_id, new_title)
                elif db_enabled:
                    # optional: implement later if you still use DB task lists
                    try:
                        db.init_db()
                        if hasattr(db, "update_task_text"):
                            db.update_task_text(chat_id, task_id, new_title)
                    except Exception:
                        pass
                else:
                    for t in state.tasks[chat_id]:
                        if t.id == task_id:
                            t.text = new_title
                            break

                state.pending.pop(chat_id, None)

                try:
                    smid = int(source_mid)
                except Exception:
                    return reply(f"Updated item {item_no}. (Could not update the list message.)")

                return [{
                    "type": "edit",
                    "chat_id": chat_id,
                    "message_id": smid,
                    "update_task": {"id": task_id, "title": new_title},
                }]

    # --- routing commands ---
    if route.get("kind") == "pick_action":
        action = route.get("action")
        mid = event.get("message_id")

        if not isinstance(mid, int):
            return reply("I can’t find the task list message. Run /today again.")

        if action == "pick_done":
            state.pending[chat_id] = {"mode": "done_pick", "source_message_id": mid}
            tasks = (state.render_cache.get((chat_id, mid)) or {}).get("tasks") or []
            n = len(tasks) if isinstance(tasks, list) else 0
            return reply(f"Which item number to mark Done? (1 to {n})")

        if action == "pick_edit":
            state.pending[chat_id] = {"mode": "edit_pick", "source_message_id": mid}
            tasks = (state.render_cache.get((chat_id, mid)) or {}).get("tasks") or []
            n = len(tasks) if isinstance(tasks, list) else 0
            return reply(f"Which item number to Edit? (1 to {n})")

        return reply("Unknown action.")

    if route.get("kind") == "command":
        cmd = route.get("command")

        if cmd == "note":
            note_text = (route.get("text") or "").strip()
            if not note_text:
                return reply("Missing text. Usage: /note <text>")

            if notion_enabled:
                page_id = notion.create_note(
                    notes_db_id,
                    title=_make_title(note_text),
                    text=note_text,
                    note_type="other",
                    tags=[],
                    labels=[],
                    source="telegram",
                    telegram_message_link=None,
                )
                _save_message_map("note", page_id)
                return reply(
                    f"Saved note (Notion): {page_id}",
                    reply_markup=_open_in_notion_markup(page_id),
                    disable_web_page_preview=True,
                )

            if db_enabled:
                db.init_db()
                nid = db.create_note(chat_id, note_text)
                return reply(f"Saved note: {nid}")

            nid = _next_id(state, "note")
            state.notes[chat_id].append(Note(id=nid, text=note_text, created_at=_now_iso()))
            return reply(f"Saved note: {nid}")

        if cmd == "todo":
            task_text = (route.get("text") or "").strip()
            if not task_text:
                return reply("Missing text. Usage: /todo <text>")

            if notion_enabled:
                page_id = notion.create_task(
                    tasks_db_id,
                    title=task_text,
                    status="todo",
                    due=None,
                    priority="med",
                    labels=[],
                    source="telegram",
                    source_note_page_ids=None,
                )
                _save_message_map("task", page_id)
                return reply(
                    f"Added task (Notion): {page_id}",
                    reply_markup=_open_in_notion_markup(page_id),
                    disable_web_page_preview=True,
                )

            if db_enabled:
                db.init_db()
                tid = db.create_task(chat_id, task_text)
                return reply(f"Added task: {tid}")

            tid = _next_id(state, "task")
            state.tasks[chat_id].append(Task(id=tid, text=task_text, created_at=_now_iso()))
            return reply(f"Added task: {tid}")

        if cmd == "today":
            if notion_enabled:
                tasks = notion.list_open_tasks(tasks_db_id, limit=5)
                if not tasks:
                    return reply("No open tasks. Go touch grass 🌱")

                lines = []
                rendered_tasks = []

                for i, t in enumerate(tasks, start=1):
                    tid = t["id"]
                    title = (t.get("title") or "").strip()
                    due = t.get("due")
                    status = t.get("status") or "todo"

                    due_txt = f" (due {due})" if due else ""
                    lines.append(f"{i}. {title}{due_txt}")

                    rendered_tasks.append({"id": tid, "title": title, "due": due, "status": status})

                text_out = f"Open tasks: {len(tasks)}\n" + "\n".join(lines)

                return [
                    {
                        "type": "reply",
                        "chat_id": chat_id,
                        "text": text_out,
                        "reply_markup": _two_button_task_list_markup(),
                        "disable_web_page_preview": True,
                    },
                    {
                        "type": "cache_task_list",
                        "chat_id": chat_id,
                        "list_kind": "today",
                        "tasks": rendered_tasks,
                        "text": text_out,
                    },
                ]

            if db_enabled:
                db.init_db()
                open_tasks = db.list_open_tasks(chat_id, limit=5)
                if not open_tasks:
                    return reply("No open tasks. Go touch grass 🌱")
                preview = "\n".join([f"- {t['id']}: {t['text']}" for t in open_tasks])
                return reply(f"Open tasks: {len(open_tasks)}\n{preview}")

            open_tasks = [t for t in state.tasks[chat_id] if not t.done]
            if not open_tasks:
                return reply("No open tasks. Go touch grass 🌱")
            preview = "\n".join([f"- {t.id}: {t.text}" for t in open_tasks[-5:]])
            return reply(f"Open tasks: {len(open_tasks)}\n{preview}")

        if cmd == "inbox":
            if notion_enabled:
                tasks = notion.list_inbox_tasks(tasks_db_id, limit=20)
                if not tasks:
                    return reply("Inbox is empty. Suspiciously productive. 😎")

                lines = []
                rendered_tasks = []

                for i, t in enumerate(tasks, start=1):
                    tid = t["id"]
                    title = (t.get("title") or "").strip()
                    due = t.get("due")
                    status = t.get("status") or "todo"
                    due_txt = f" (due {due})" if due else ""
                    lines.append(f"{i}. [{status}] {title}{due_txt}")

                    rendered_tasks.append({"id": tid, "title": title, "due": due, "status": status})

                text_out = "Inbox (open tasks):\n" + "\n".join(lines)

                return [
                    {
                        "type": "reply",
                        "chat_id": chat_id,
                        "text": text_out,
                        "reply_markup": _two_button_task_list_markup(),
                        "disable_web_page_preview": True,
                    },
                    {
                        "type": "cache_task_list",
                        "chat_id": chat_id,
                        "list_kind": "inbox",
                        "tasks": rendered_tasks,
                        "text": text_out,
                    },
                ]

            if db_enabled:
                db.init_db()
                open_tasks = db.list_open_tasks(chat_id, limit=20)
                if not open_tasks:
                    return reply("Inbox is empty. Suspiciously productive. 😎")
                preview = "\n".join([f"- {t['id']}: {t['text']}" for t in open_tasks])
                return reply("Inbox (open tasks):\n" + preview)

            open_tasks = [t for t in state.tasks[chat_id] if not t.done]
            if not open_tasks:
                return reply("Inbox is empty. Suspiciously productive. 😎")
            preview = "\n".join([f"- {t.id}: {t.text}" for t in open_tasks[-20:]])
            return reply("Inbox (open tasks):\n" + preview)

        if cmd == "done":
            task_id = (route.get("task_id") or "").strip()
            if not task_id:
                return reply("Missing task id. Usage: /done <task_id>")

            if notion_enabled:
                ok = notion.mark_task_done(task_id)
                if not ok:
                    return reply(f"Task not found (Notion): {task_id}")

                if et == "callback" and isinstance(event.get("message_id"), int):
                    return [{
                        "type": "edit",
                        "chat_id": chat_id,
                        "message_id": int(event["message_id"]),
                        "remove_task_id": task_id,
                    }]

                return reply(f"Marked done (Notion): {task_id}")

            if db_enabled:
                db.init_db()
                ok = db.mark_task_done(chat_id, task_id)
                if not ok:
                    return reply(f"Task not found (or already done): {task_id}")

                if et == "callback" and isinstance(event.get("message_id"), int):
                    return [{
                        "type": "edit",
                        "chat_id": chat_id,
                        "message_id": int(event["message_id"]),
                        "remove_task_id": task_id,
                    }]

                return reply(f"Marked done: {task_id}")

            found = False
            for t in state.tasks[chat_id]:
                if t.id == task_id:
                    if t.done:
                        return reply(f"{task_id} is already done.")
                    t.done = True
                    found = True
                    break

            if not found:
                return reply(f"Task not found: {task_id}")

            if et == "callback" and isinstance(event.get("message_id"), int):
                return [{
                    "type": "edit",
                    "chat_id": chat_id,
                    "message_id": int(event["message_id"]),
                    "remove_task_id": task_id,
                }]

            return reply(f"Marked done: {task_id}")

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

        if cmd == "settings":
            raw = (event.get("text") or "").strip()
            parts = raw.split()

            if db_enabled:
                db.init_db()

            def _get(k: str, default: str = "") -> str:
                if not db_enabled:
                    return default
                v = db.get_setting(k, default)
                return "" if v is None else str(v)

            def _set(k: str, v: str) -> None:
                if not db_enabled:
                    return
                db.set_setting(k, v)

            if len(parts) >= 4 and parts[1] == "set":
                key = parts[2].strip()
                value = " ".join(parts[3:]).strip()

                allowed = {"timezone", "daily_brief_time", "privacy_mode", "ai_enabled"}
                if key not in allowed:
                    return reply(f"Invalid key. Allowed: {', '.join(sorted(allowed))}")

                if key == "daily_brief_time":
                    if len(value) != 5 or value[2] != ":":
                        return reply("daily_brief_time must be HH:MM (e.g., 07:30)")
                if key == "ai_enabled":
                    v2 = value.lower()
                    if v2 in {"1", "true", "yes", "on"}:
                        value = "true"
                    elif v2 in {"0", "false", "no", "off"}:
                        value = "false"
                    else:
                        return reply("ai_enabled must be true/false")

                _set(key, value)
                return reply(f"Updated {key} = {value}")

            tz = _get("timezone", "Asia/Singapore")
            brief = _get("daily_brief_time", "07:30")
            privacy = _get("privacy_mode", "A")
            ai_enabled = _get("ai_enabled", "true")

            return reply(
                "Settings:\n"
                f"- timezone: {tz}\n"
                f"- daily_brief_time: {brief}\n"
                f"- privacy_mode: {privacy}\n"
                f"- ai_enabled: {ai_enabled}\n\n"
                "Update with:\n"
                "/settings set <key> <value>\n"
                "Keys: timezone, daily_brief_time, privacy_mode, ai_enabled"
            )

        if cmd == "help":
            return reply(
                "Commands:\n"
                "/note <text>\n"
                "/todo <text>\n"
                "/inbox\n"
                "/today\n"
                "/done <task_id>\n"
                "/settings\n"
                "/search <query>"
            )

        return reply(f"Command not implemented yet: /{cmd}")

    # Plain text -> note capture (ONLY for message events)
    if et == "message" and route.get("kind") == "text":
        note_text = (route.get("text") or "").strip()
        if not note_text:
            return reply("Empty message")

        if notion_enabled:
            page_id = notion.create_note(
                notes_db_id,
                title=_make_title(note_text),
                text=note_text,
                note_type="other",
                tags=[],
                labels=[],
                source="telegram",
                telegram_message_link=None,
            )
            _save_message_map("note", page_id)
            return reply(
                f"Saved note (Notion): {page_id}",
                reply_markup=_open_in_notion_markup(page_id),
                disable_web_page_preview=True,
            )

        if db_enabled:
            db.init_db()
            nid = db.create_note(chat_id, note_text)
            return reply(f"Saved note: {nid}")

        nid = _next_id(state, "note")
        state.notes[chat_id].append(Note(id=nid, text=note_text, created_at=_now_iso()))
        return reply(f"Saved note: {nid}")

    if route.get("kind") == "unknown_command":
        return reply(f"Unknown command: /{route.get('command')} (try /help)")

    if route.get("kind") == "error":
        return reply(route.get("message", "Error"))

    return []



