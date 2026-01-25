# notion.py
from __future__ import annotations

import os
from typing import Dict

def page_url(page_id: str) -> str:
    """
    Build a Notion URL from a page_id.

    Notion canonical URLs usually include a title slug + page id, but the bare
    page id is enough to open the page in a browser.

    Accepts:
      - UUID with hyphens (xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)
      - 32-hex without hyphens

    Returns:
      https://www.notion.so/<32-hex>
    """
    pid = (page_id or "").strip()
    if not pid:
        raise ValueError("page_id must be non-empty")

    # keep only hex chars, drop hyphens/garbage
    hex_only = "".join([c for c in pid if c.lower() in "0123456789abcdef"])
    if len(hex_only) < 32:
        # fall back to raw (best effort) rather than hard failing
        hex_only = pid.replace("-", "")
    return f"https://www.notion.so/{hex_only}"

def page_url(page_id: str) -> str:
    """
    Build a Notion URL from a page_id.

    Notion accepts a bare page id (32 hex chars, no hyphens) in the URL path.
    This is good enough for an "Open in Notion" button.

    Returns:
      https://www.notion.so/<32-hex>
    """
    pid = (page_id or "").strip()
    if not pid:
        raise ValueError("page_id must be non-empty")

    # keep only hex chars, drop hyphens and anything weird
    hex_only = "".join([c for c in pid.lower() if c in "0123456789abcdef"])

    # Best-effort: if page_id isn't UUID-like, fall back to something usable
    if len(hex_only) < 32:
        hex_only = pid.replace("-", "")

    return f"https://www.notion.so/{hex_only}"


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

    LIVE NOTES DB properties (confirmed by your API call):
      - Title (title)
      - Body (rich_text)
      - Labels (multi_select)
      - Source (select)
      - CreatedAt (created_time)

    So we MUST ONLY send: Title, Body, Labels, Source.
    Anything else will 400 validation_error.

    Also: pin Notion-Version to 2022-06-28 and sanitize token to remove CR/LF.
    """
    import os
    import requests

    raw_token = os.getenv("NOTION_TOKEN") or ""
    token = raw_token.strip().replace("\r", "").replace("\n", "")
    if not token:
        raise RuntimeError("NOTION_TOKEN is not configured")

    # Pin version (ignore env to prevent surprises)
    notion_version = "2022-06-28"

    notes_db_id = (notes_db_id or "").strip()
    if not notes_db_id:
        raise ValueError("notes_db_id must be non-empty")

    title = (title or "").strip()
    if not title:
        raise ValueError("title must be non-empty")

    text = (text or "").strip()
    if not text:
        raise ValueError("text must be non-empty")

    source_name = (source or "telegram").strip() or "telegram"

    # Optionally preserve the Telegram link WITHOUT breaking schema
    if telegram_message_link:
        text = f"{text}\n\nTelegram: {telegram_message_link}".strip()

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": notion_version,
        "Content-Type": "application/json",
    }

    body_rich_text = [{"type": "text", "text": {"content": chunk}} for chunk in _chunk_text(text)]
    if not body_rich_text:
        body_rich_text = [{"type": "text", "text": {"content": text}}]

    props: dict = {
        "Title": {"title": [{"type": "text", "text": {"content": title}}]},
        "Body": {"rich_text": body_rich_text},
        "Source": {"select": {"name": source_name}},
    }

    if labels:
        props["Labels"] = {"multi_select": [{"name": l.strip()} for l in labels if l and l.strip()]}

    payload = {"parent": {"database_id": notes_db_id}, "properties": props}

    r = requests.request(
        "POST",
        "https://api.notion.com/v1/pages",
        headers=headers,
        json=payload,
        timeout=30,
    )
    if r.status_code not in (200, 201):
        snippet = (r.text or "")[:500]
        raise RuntimeError(f"Notion API error {r.status_code} creating note: {snippet}")

    data = r.json() or {}
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


def create_task(
    tasks_db_id: str,
    *,
    title: str,
    status: str = "todo",
    due: str | None = None,
    priority: str = "med",
    labels: list[str] | None = None,
    source: str = "telegram",
    source_note_page_ids: list[str] | None = None,
) -> str:
    """
    Create a task page in the Tasks DB.

    Resilience:
    - Some Notion Task DBs use Status as a Notion *status* property:
        "Status": {"status": {"name": "<option>"}}
    - Others use Status as a *select* property:
        "Status": {"select": {"name": "<option>"}}

    We try status-type first, then fall back to select-type on 400 validation errors.

    Cloud Run gotcha:
    - Secret Manager values can contain trailing newline/CRLF.
    - requests will crash if headers contain \\r or \\n.
    """
    import os
    import requests

    raw_token = os.getenv("NOTION_TOKEN") or ""
    token = raw_token.strip().replace("\r", "").replace("\n", "")
    if not token:
        raise RuntimeError("NOTION_TOKEN is not set")

    notion_version = (os.getenv("NOTION_VERSION") or "2022-06-28").strip() or "2022-06-28"

    tasks_db_id = (tasks_db_id or "").strip()
    if not tasks_db_id:
        raise ValueError("tasks_db_id is required")

    if not title or not title.strip():
        raise ValueError("title is required")

    status_name = (status or "todo").strip()
    priority_name = (priority or "med").strip()
    source_name = (source or "telegram").strip()

    base_props: dict = {
        "Title": {"title": [{"type": "text", "text": {"content": title.strip()}}]},
        "Priority": {"select": {"name": priority_name}},
        "Source": {"select": {"name": source_name}},
    }

    if due:
        base_props["Due"] = {"date": {"start": str(due).strip()}}

    if labels:
        base_props["Labels"] = {
            "multi_select": [{"name": x.strip()} for x in labels if x and x.strip()]
        }

    if source_note_page_ids:
        base_props["Source Notes"] = {"relation": [{"id": pid} for pid in source_note_page_ids if pid]}

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": notion_version,
        "Content-Type": "application/json",
    }

    def _post_with_status_kind(kind: str):
        props = dict(base_props)
        if kind == "status":
            props["Status"] = {"status": {"name": status_name}}
        else:
            props["Status"] = {"select": {"name": status_name}}

        payload = {"parent": {"database_id": tasks_db_id}, "properties": props}

        r = requests.request(
            "POST",
            "https://api.notion.com/v1/pages",
            headers=headers,
            json=payload,
            timeout=30,
        )
        return r

    # 1) Try status-type first (common for many live DBs)
    r1 = _post_with_status_kind("status")
    if r1.status_code in (200, 201):
        return r1.json()["id"]

    # 2) If validation error, try select-type fallback
    if r1.status_code == 400:
        r2 = _post_with_status_kind("select")
        if r2.status_code in (200, 201):
            return r2.json()["id"]

        snippet2 = (getattr(r2, "text", "") or "")[:500]
        snippet1 = (getattr(r1, "text", "") or "")[:500]
        raise RuntimeError(
            f"Notion API error creating task (status->select fallback failed). "
            f"status_resp={r1.status_code}:{snippet1} | select_resp={r2.status_code}:{snippet2}"
        )

    snippet1 = (getattr(r1, "text", "") or "")[:500]
    raise RuntimeError(f"Notion API error {r1.status_code} creating task: {snippet1}")


def list_open_tasks(tasks_db_id: str, *, limit: int = 10) -> list[dict]:
    """
    Query Tasks DB for open tasks (Status != done), sorted by Due ascending.
    Returns simplified list: [{"id": page_id, "title": "...", "status": "...", "due": "..."}]

    Compatibility hardening:
    - Some Notion Task DBs model Status as a Notion "status" property.
    - Others model Status as a "select" property (as in older schemas / some PRDs).
    - Notion will 400 if filter type doesn't match property type.
      So we try "status" filter first, then fall back to "select" filter if we detect a mismatch.

    Also:
    - Pin Notion-Version to 2022-06-28 for stable /databases/{db_id}/query behavior.
    - Sanitize NOTION_TOKEN to remove CR/LF (Secret Manager newline gotcha).
    """
    import os
    import requests

    raw_token = os.getenv("NOTION_TOKEN") or ""
    token = raw_token.strip().replace("\r", "").replace("\n", "")
    if not token:
        raise RuntimeError("NOTION_TOKEN is not configured")

    notion_version = "2022-06-28"

    tasks_db_id = (tasks_db_id or "").strip()
    if not tasks_db_id:
        raise ValueError("tasks_db_id must be non-empty")

    # Normalize limit
    try:
        limit_i = int(limit)
    except Exception:
        limit_i = 10
    if limit_i <= 0:
        limit_i = 10

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": notion_version,
        "Content-Type": "application/json",
    }

    def _do_query(payload: dict) -> requests.Response:
        return requests.request(
            "POST",
            f"https://api.notion.com/v1/databases/{tasks_db_id}/query",
            headers=headers,
            json=payload,
            timeout=30,
        )

    # Try Status as a Notion "status" property first
    payload_status = {
        "page_size": limit_i,
        "filter": {
            "and": [
                {"property": "Status", "status": {"does_not_equal": "done"}},
                {"property": "Status", "status": {"does_not_equal": "Done"}},
            ]
        },
        "sorts": [{"property": "Due", "direction": "ascending"}],
    }

    r = _do_query(payload_status)

    # If 400 and looks like a schema/type mismatch, retry as "select"
    if r.status_code == 400:
        body = (getattr(r, "text", "") or "").lower()
        looks_like_type_mismatch = (
            "does not match filter" in body
            or ("status" in body and "select" in body)
            or ("property" in body and "status" in body and "filter" in body)
        )
        if looks_like_type_mismatch:
            payload_select = {
                "page_size": limit_i,
                "filter": {
                    "and": [
                        {"property": "Status", "select": {"does_not_equal": "done"}},
                        {"property": "Status", "select": {"does_not_equal": "Done"}},
                    ]
                },
                "sorts": [{"property": "Due", "direction": "ascending"}],
            }
            r = _do_query(payload_select)

    if r.status_code >= 400:
        snippet = (getattr(r, "text", "") or "")[:500]
        raise RuntimeError(f"Notion API error {r.status_code} querying tasks: {snippet}")

    data = r.json() or {}
    results = data.get("results") or []

    out: list[dict] = []
    for page in results:
        pid = page.get("id")
        props = (page.get("properties") or {})

        # Title
        title = ""
        try:
            tarr = props.get("Title", {}).get("title", [])
            if tarr and isinstance(tarr, list):
                title = (tarr[0].get("plain_text") or "").strip()
        except Exception:
            title = ""

        # Status (support both status and select)
        status = ""
        try:
            status_obj = props.get("Status", {}) or {}
            status = (
                ((status_obj.get("status") or {}).get("name"))
                or ((status_obj.get("select") or {}).get("name"))
                or ""
            )
        except Exception:
            status = ""

        # Due
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
    Sets Status=done on a task page.
    Tries to set Completed At=now (UTC) too, but falls back if the property doesn't exist.

    Compatibility hardening:
    - Some Task DBs model Status as Notion "status"
    - Others model Status as "select"
    - Notion hard-fails with 400 if property type doesn't match the payload

    Strategy:
    Try these in order until one succeeds:
      1) Status as "status" + Completed At
      2) Status as "status" only
      3) Status as "select" + Completed At
      4) Status as "select" only
    """
    import os
    import requests
    from datetime import datetime, timezone

    raw_token = os.getenv("NOTION_TOKEN") or ""
    token = raw_token.strip().replace("\r", "").replace("\n", "")
    if not token:
        raise RuntimeError("NOTION_TOKEN is not set")

    notion_version = (os.getenv("NOTION_VERSION") or "2022-06-28").strip() or "2022-06-28"

    page_id = (page_id or "").strip()
    if not page_id:
        raise ValueError("page_id is required")

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": notion_version,
        "Content-Type": "application/json",
    }

    completed_at_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _payload(status_kind: str, include_completed_at: bool) -> dict:
        props: dict = {}

        if status_kind == "status":
            props["Status"] = {"status": {"name": "done"}}
        else:
            props["Status"] = {"select": {"name": "done"}}

        if include_completed_at:
            # This must match the Notion property name (if it exists).
            # If it doesn't exist, Notion 400s and we retry without it.
            props["Completed At"] = {"date": {"start": completed_at_iso}}

        return {"properties": props}

    attempts = [
        ("status", True),
        ("status", False),
        ("select", True),
        ("select", False),
    ]

    last_errors: list[str] = []

    for status_kind, include_completed_at in attempts:
        payload = _payload(status_kind, include_completed_at)
        r = requests.request(
            "PATCH",
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=headers,
            json=payload,
            timeout=30,
        )

        if r.status_code in (200, 201):
            return True

        snippet = (getattr(r, "text", "") or "")[:500]
        last_errors.append(f"{status_kind}+completed={include_completed_at}: {r.status_code} {snippet}")

    raise RuntimeError("Notion API error marking done; all fallbacks failed: " + " | ".join(last_errors))


def update_task_title(page_id: str, new_title: str) -> bool:
    """
    Update a task page Title in Notion.
    Returns True on success, raises RuntimeError on failure.
    """
    import os
    import requests

    raw_token = os.getenv("NOTION_TOKEN") or ""
    token = raw_token.strip().replace("\r", "").replace("\n", "")
    if not token:
        raise RuntimeError("NOTION_TOKEN is not set")

    notion_version = (os.getenv("NOTION_VERSION") or "2022-06-28").strip() or "2022-06-28"

    page_id = (page_id or "").strip()
    if not page_id:
        raise ValueError("page_id is required")

    new_title = (new_title or "").strip()
    if not new_title:
        raise ValueError("new_title must be non-empty")

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": notion_version,
        "Content-Type": "application/json",
    }

    payload = {
        "properties": {
            "Title": {"title": [{"type": "text", "text": {"content": new_title}}]}
        }
    }

    r = requests.request(
        "PATCH",
        f"https://api.notion.com/v1/pages/{page_id}",
        headers=headers,
        json=payload,
        timeout=30,
    )

    if r.status_code in (200, 201):
        return True

    snippet = (getattr(r, "text", "") or "")[:500]
    raise RuntimeError(f"Notion API error {r.status_code} updating task title: {snippet}")


def list_inbox_tasks(tasks_db_id: str, *, limit: int = 20) -> list[dict]:
    """
    Inbox view: open tasks (Status != done), sorted by Due asc.
    Returns simplified list: [{"id": page_id, "title": "...", "status": "...", "due": "..."}]
    """
    # Reuse list_open_tasks logic but with a larger default limit.
    return list_open_tasks(tasks_db_id, limit=limit)
