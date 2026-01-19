# notion.py
from __future__ import annotations

import os
from typing import Dict


def setup_databases(parent_page_id: str) -> dict:
    """
    One-time setup:
      - Create 2 Notion databases under a parent page: "KC Notes" and "KC Tasks"
      - Create a relation between them (Tasks.Source Notes <-> Notes.Related Tasks)
      - Seed default Labels options into both DBs
      - Return {"notes_db_id": "...", "tasks_db_id": "..."} (PRD contract)
    """
    import os
    import requests

    token = (os.getenv("NOTION_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("NOTION_TOKEN is not configured")

    parent_page_id = (parent_page_id or "").strip()
    if not parent_page_id:
        raise ValueError("parent_page_id must be non-empty")

    # Notion API versioning: latest public model uses database containers + data_sources
    notion_version = (os.getenv("NOTION_VERSION") or "2025-09-03").strip()
    base_url = "https://api.notion.com/v1"

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

    def opt(name: str) -> dict:
        # 'color' is optional in some cases but safe to include.
        return {"name": name, "color": "default"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": notion_version,
        "Content-Type": "application/json",
    }

    def _request(method: str, path: str, payload: dict | None = None) -> dict:
        url = f"{base_url}{path}"
        r = requests.request(method, url, headers=headers, json=payload, timeout=20)
        if r.status_code >= 400:
            # Keep it readable; do not dump headers or secrets.
            snippet = (r.text or "")[:500]
            raise RuntimeError(f"Notion API error {r.status_code} for {method} {path}: {snippet}")
        if not r.content:
            return {}
        return r.json()

    def _get_first_data_source_id(db_obj: dict) -> str:
        # Newer versions: database object exposes data_sources array
        ds = db_obj.get("data_sources")
        if isinstance(ds, list) and ds:
            ds0 = ds[0]
            if isinstance(ds0, dict) and ds0.get("id"):
                return ds0["id"]

        # Fallback for some responses/tooling
        init_ds = db_obj.get("initial_data_source")
        if isinstance(init_ds, dict) and init_ds.get("id"):
            return init_ds["id"]

        raise RuntimeError("Could not determine data_source_id from Notion database create response")

    def _create_db(db_title: str, properties: dict) -> dict:
        payload = {
            "parent": {"type": "page_id", "page_id": parent_page_id},
            "title": [{"type": "text", "text": {"content": db_title}}],
            "properties": properties,
        }
        return _request("POST", "/databases", payload)

    # PRD-required Notes DB schema
    notes_properties = {
        "Title": {"title": {}},
        "Type": {
            "select": {
                "options": [
                    opt("meeting"),
                    opt("research"),
                    opt("receipt"),
                    opt("tech"),
                    opt("personal"),
                    opt("other"),
                ]
            }
        },
        "Tags": {"multi_select": {"options": []}},
        "Labels": {"multi_select": {"options": [opt(x) for x in default_labels]}},
        "Source": {"select": {"options": [opt("telegram"), opt("web")]}},
        "Telegram Message Link": {"url": {}},
        "AI Structured": {"checkbox": {}},
        "AI Summary": {"rich_text": {}},
        "AI Bullets": {"rich_text": {}},
        # "Related Tasks" will be created as the synced side of the Tasks relation.
    }

    # PRD-required Tasks DB schema
    tasks_properties = {
        "Title": {"title": {}},
        "Status": {"select": {"options": [opt("todo"), opt("doing"), opt("done")]}},
        "Due": {"date": {}},
        "Priority": {"select": {"options": [opt("low"), opt("med"), opt("high")]}},
        "Labels": {"multi_select": {"options": [opt(x) for x in default_labels]}},
        "Source": {"select": {"options": [opt("telegram"), opt("note_extraction"), opt("web")]}},
        "Completed At": {"date": {}},
        "Confidence": {"number": {}},
        "Needs Review": {"checkbox": {}},
        "AI Rationale": {"rich_text": {}},
        # Relation added AFTER both DBs exist:
        # "Source Notes" (relation to Notes) and synced "Related Tasks" on Notes side.
    }

    notes_db = _create_db("KC Notes", notes_properties)
    notes_db_id = notes_db.get("id")
    if not notes_db_id:
        raise RuntimeError("Notion create database response missing notes DB id")
    notes_ds_id = _get_first_data_source_id(notes_db)

    tasks_db = _create_db("KC Tasks", tasks_properties)
    tasks_db_id = tasks_db.get("id")
    if not tasks_db_id:
        raise RuntimeError("Notion create database response missing tasks DB id")
    tasks_ds_id = _get_first_data_source_id(tasks_db)

    # Create the relation:
    # Tasks: "Source Notes" -> Notes
    # Notes gets synced property "Related Tasks"
    _request(
        "PATCH",
        f"/data_sources/{tasks_ds_id}",
        {
            "properties": {
                "Source Notes": {
                    "type": "relation",
                    "relation": {
                        "data_source_id": notes_ds_id,
                        "dual_property": {"synced_property_name": "Related Tasks"},
                    },
                }
            }
        },
    )

    return {"notes_db_id": notes_db_id, "tasks_db_id": tasks_db_id}


def _chunk_text(text: str, chunk_size: int = 1800) -> list[str]:
    """
    Notion block rich_text content has practical size limits.
    We keep chunks conservative to avoid 400 errors on long notes.
    """
    text = (text or "").strip()
    if not text:
        return []
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def create_note(
    notes_db_id: str,
    *,
    title: str,
    text: str,
    note_type: str = "other",
    tags: list[str] | None = None,
    labels: list[str] | None = None,
    source: str = "telegram",
    telegram_message_link: str | None = None,
) -> str:
    """
    Creates a Note page inside the Notes DB.
    Returns Notion page_id.

    Stores the full note content in page blocks (children).
    """
    import os
    import requests

    token = (os.getenv("NOTION_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("NOTION_TOKEN is not configured")

    notion_version = (os.getenv("NOTION_VERSION") or "2025-09-03").strip()
    base_url = "https://api.notion.com/v1"

    notes_db_id = (notes_db_id or "").strip()
    if not notes_db_id:
        raise ValueError("notes_db_id must be non-empty")

    title = (title or "").strip()
    if not title:
        raise ValueError("title must be non-empty")

    text = (text or "").strip()
    if not text:
        raise ValueError("text must be non-empty")

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": notion_version,
        "Content-Type": "application/json",
    }

    props: dict = {
        "Title": {"title": [{"type": "text", "text": {"content": title}}]},
        "Type": {"select": {"name": (note_type or "other")}},
        "Source": {"select": {"name": (source or "telegram")}},
        "AI Structured": {"checkbox": False},
    }

    if tags:
        props["Tags"] = {"multi_select": [{"name": t} for t in tags if str(t).strip()]}

    if labels:
        props["Labels"] = {"multi_select": [{"name": l} for l in labels if str(l).strip()]}

    if telegram_message_link:
        props["Telegram Message Link"] = {"url": str(telegram_message_link)}

    children = []
    for chunk in _chunk_text(text):
        children.append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]},
            }
        )

    payload = {"parent": {"database_id": notes_db_id}, "properties": props, "children": children}

    r = requests.request("POST", f"{base_url}/pages", headers=headers, json=payload, timeout=20)
    if r.status_code >= 400:
        snippet = (r.text or "")[:500]
        raise RuntimeError(f"Notion API error {r.status_code} creating note: {snippet}")

    data = r.json()
    page_id = data.get("id")
    if not page_id:
        raise RuntimeError("Notion create note response missing page id")

    return page_id


def _chunk_text(text: str, chunk_size: int = 1800) -> list[str]:
    """
    Notion block rich_text content has practical size limits.
    We keep chunks conservative to avoid 400 errors on long notes.
    """
    text = (text or "").strip()
    if not text:
        return []
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]


def create_note(
    notes_db_id: str,
    *,
    title: str,
    text: str,
    note_type: str = "other",
    tags: list[str] | None = None,
    labels: list[str] | None = None,
    source: str = "telegram",
    telegram_message_link: str | None = None,
) -> str:
    """
    Creates a Note page inside the Notes DB.
    Returns Notion page_id.

    Stores the full note content in page blocks (children).
    """
    import os
    import requests

    token = (os.getenv("NOTION_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("NOTION_TOKEN is not configured")

    notion_version = (os.getenv("NOTION_VERSION") or "2025-09-03").strip()
    base_url = "https://api.notion.com/v1"

    notes_db_id = (notes_db_id or "").strip()
    if not notes_db_id:
        raise ValueError("notes_db_id must be non-empty")

    title = (title or "").strip()
    if not title:
        raise ValueError("title must be non-empty")

    text = (text or "").strip()
    if not text:
        raise ValueError("text must be non-empty")

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": notion_version,
        "Content-Type": "application/json",
    }

    props: dict = {
        "Title": {"title": [{"type": "text", "text": {"content": title}}]},
        "Type": {"select": {"name": (note_type or "other")}},
        "Source": {"select": {"name": (source or "telegram")}},
        "AI Structured": {"checkbox": False},
    }

    if tags:
        props["Tags"] = {"multi_select": [{"name": t} for t in tags if str(t).strip()]}

    if labels:
        props["Labels"] = {"multi_select": [{"name": l} for l in labels if str(l).strip()]}

    if telegram_message_link:
        props["Telegram Message Link"] = {"url": str(telegram_message_link)}

    children = []
    for chunk in _chunk_text(text):
        children.append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": chunk}}]},
            }
        )

    payload = {"parent": {"database_id": notes_db_id}, "properties": props, "children": children}

    r = requests.request("POST", f"{base_url}/pages", headers=headers, json=payload, timeout=20)
    if r.status_code >= 400:
        snippet = (r.text or "")[:500]
        raise RuntimeError(f"Notion API error {r.status_code} creating note: {snippet}")

    data = r.json()
    page_id = data.get("id")
    if not page_id:
        raise RuntimeError("Notion create note response missing page id")

    return page_id


def create_task(
    tasks_db_id: str,
    *,
    title: str,
    status: str = "todo",
    due: str | None = None,  # ISO date or datetime string (we store as start)
    priority: str = "med",
    labels: list[str] | None = None,
    source: str = "telegram",
    source_note_page_ids: list[str] | None = None,
) -> str:
    """
    Creates a Task page inside the Tasks DB.
    Returns Notion page_id.
    """
    import os
    import requests

    token = (os.getenv("NOTION_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("NOTION_TOKEN is not configured")

    notion_version = (os.getenv("NOTION_VERSION") or "2025-09-03").strip()
    base_url = "https://api.notion.com/v1"

    tasks_db_id = (tasks_db_id or "").strip()
    if not tasks_db_id:
        raise ValueError("tasks_db_id must be non-empty")

    title = (title or "").strip()
    if not title:
        raise ValueError("title must be non-empty")

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": notion_version,
        "Content-Type": "application/json",
    }

    props: dict = {
        "Title": {"title": [{"type": "text", "text": {"content": title}}]},
        "Status": {"select": {"name": (status or "todo")}},
        "Priority": {"select": {"name": (priority or "med")}},
        "Source": {"select": {"name": (source or "telegram")}},
    }

    if labels:
        props["Labels"] = {"multi_select": [{"name": l} for l in labels if str(l).strip()]}

    if due:
        props["Due"] = {"date": {"start": str(due)}}

    if source_note_page_ids:
        # Relation property created during setup: "Source Notes"
        props["Source Notes"] = {"relation": [{"id": pid} for pid in source_note_page_ids if str(pid).strip()]}

    payload = {"parent": {"database_id": tasks_db_id}, "properties": props}

    r = requests.request("POST", f"{base_url}/pages", headers=headers, json=payload, timeout=20)
    if r.status_code >= 400:
        snippet = (r.text or "")[:500]
        raise RuntimeError(f"Notion API error {r.status_code} creating task: {snippet}")

    data = r.json()
    page_id = data.get("id")
    if not page_id:
        raise RuntimeError("Notion create task response missing page id")

    return page_id


def list_open_tasks(tasks_db_id: str, *, limit: int = 10) -> list[dict]:
    """
    Query KC Tasks for open tasks (Status != done), sorted by Due ascending.
    Returns simplified list: [{"id": page_id, "title": "...", "status": "...", "due": "..."}]
    """
    import os
    import requests

    token = (os.getenv("NOTION_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("NOTION_TOKEN is not configured")

    notion_version = (os.getenv("NOTION_VERSION") or "2025-09-03").strip()
    base_url = "https://api.notion.com/v1"

    tasks_db_id = (tasks_db_id or "").strip()
    if not tasks_db_id:
        raise ValueError("tasks_db_id must be non-empty")

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": notion_version,
        "Content-Type": "application/json",
    }

    payload = {
        "page_size": int(limit),
        "filter": {
            "and": [
                {"property": "Status", "select": {"does_not_equal": "done"}},
            ]
        },
        "sorts": [{"property": "Due", "direction": "ascending"}],
    }

    r = requests.request("POST", f"{base_url}/databases/{tasks_db_id}/query", headers=headers, json=payload, timeout=20)
    if r.status_code >= 400:
        snippet = (r.text or "")[:500]
        raise RuntimeError(f"Notion API error {r.status_code} querying tasks: {snippet}")

    data = r.json() or {}
    results = data.get("results") or []

    out: list[dict] = []
    for page in results:
        pid = page.get("id")
        props = (page.get("properties") or {})

        title = ""
        try:
            tarr = props.get("Title", {}).get("title", [])
            if tarr and isinstance(tarr, list):
                title = (tarr[0].get("plain_text") or "").strip()
        except Exception:
            title = ""

        status = ""
        try:
            status = (props.get("Status", {}).get("select") or {}).get("name") or ""
        except Exception:
            status = ""

        due = None
        try:
            due = (props.get("Due", {}).get("date") or {}).get("start")
        except Exception:
            due = None

        if pid:
            out.append({"id": pid, "title": title, "status": status, "due": due})

    return out


def mark_task_done(page_id: str) -> bool:
    """
    Sets Status=done and Completed At=now (UTC) on a task page.
    Returns True if successful.
    """
    import os
    import requests
    from datetime import datetime, timezone

    token = (os.getenv("NOTION_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("NOTION_TOKEN is not configured")

    notion_version = (os.getenv("NOTION_VERSION") or "2025-09-03").strip()
    base_url = "https://api.notion.com/v1"

    page_id = (page_id or "").strip()
    if not page_id:
        raise ValueError("page_id must be non-empty")

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": notion_version,
        "Content-Type": "application/json",
    }

    now = datetime.now(timezone.utc).isoformat()

    payload = {
        "properties": {
            "Status": {"select": {"name": "done"}},
            "Completed At": {"date": {"start": now}},
        }
    }

    r = requests.request("PATCH", f"{base_url}/pages/{page_id}", headers=headers, json=payload, timeout=20)
    if r.status_code >= 400:
        snippet = (r.text or "")[:500]
        raise RuntimeError(f"Notion API error {r.status_code} marking done: {snippet}")

    return True

def list_inbox_tasks(tasks_db_id: str, *, limit: int = 20) -> list[dict]:
    """
    Inbox view: open tasks (Status != done), sorted by Due asc.
    Returns simplified list: [{"id": page_id, "title": "...", "status": "...", "due": "..."}]
    """
    # Reuse list_open_tasks logic but with a larger default limit.
    return list_open_tasks(tasks_db_id, limit=limit)
