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
    description: str | None = None,
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

    # NEW: Description (rich_text)
    if description is not None:
        desc = str(description).strip()
        if desc:
            base_props["Description"] = {
                "rich_text": [{"type": "text", "text": {"content": desc}}]
            }

    if due:
        base_props["Due"] = {"date": {"start": str(due).strip()}}

    if labels:
        base_props["Labels"] = {
            "multi_select": [{"name": x.strip()} for x in labels if x and x.strip()]
        }

    if source_note_page_ids:
        base_props["Source Notes"] = {
            "relation": [{"id": pid} for pid in source_note_page_ids if pid]
        }

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

        payload = {
            "parent": {"database_id": tasks_db_id},
            "properties": props,
        }

        return requests.request(
            "POST",
            "https://api.notion.com/v1/pages",
            headers=headers,
            json=payload,
            timeout=30,
        )

    # Try Status as `status` first
    r = _post_with_status_kind("status")
    if r.status_code in (200, 201):
        return (r.json() or {}).get("id") or ""

    # Fallback: Status as `select` if Notion validation complains
    if r.status_code == 400:
        r2 = _post_with_status_kind("select")
        if r2.status_code in (200, 201):
            return (r2.json() or {}).get("id") or ""
        snippet2 = (getattr(r2, "text", "") or "")[:500]
        snippet1 = (getattr(r, "text", "") or "")[:500]
        raise RuntimeError(f"Notion create_task failed (status->select retry). {snippet1} / {snippet2}")

    snippet = (getattr(r, "text", "") or "")[:500]
    raise RuntimeError(f"Notion create_task failed. HTTP {r.status_code}: {snippet}")


def list_open_tasks(tasks_db_id: str, limit: int = 5) -> list[dict]:
    """
    Return open tasks from the Tasks DB.

    Behavior:
    - Tries Notion `status` filter first.
    - If Notion rejects it (expects select), retries with `select`.
    - Extracts:
        Title  -> "title"
        Description (rich_text) -> "description"
        Status -> "status"
        Due -> "due"

    Backward compatibility:
    - If Description is empty, and Title contains " | " or " : ",
      split Title into (title, description).
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

    limit_i = int(limit or 5)
    if limit_i < 1:
        limit_i = 1

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": notion_version,
        "Content-Type": "application/json",
    }

    def _extract_plain_text(rich_list) -> str:
        if not isinstance(rich_list, list):
            return ""
        parts = []
        for seg in rich_list:
            if not isinstance(seg, dict):
                continue
            pt = seg.get("plain_text")
            if isinstance(pt, str) and pt:
                parts.append(pt)
                continue
            txt = seg.get("text") or {}
            if isinstance(txt, dict):
                c = txt.get("content")
                if isinstance(c, str) and c:
                    parts.append(c)
        return "".join(parts).strip()

    def _pick_title(props: dict) -> str:
        if not isinstance(props, dict):
            return ""
        t = props.get("Title")
        if isinstance(t, dict):
            if "title" in t:
                return _extract_plain_text(t.get("title"))
            if "rich_text" in t:
                return _extract_plain_text(t.get("rich_text"))
        n = props.get("Name")
        if isinstance(n, dict):
            if "title" in n:
                return _extract_plain_text(n.get("title"))
            if "rich_text" in n:
                return _extract_plain_text(n.get("rich_text"))
        for v in props.values():
            if isinstance(v, dict) and "title" in v:
                s = _extract_plain_text(v.get("title"))
                if s:
                    return s
        return ""

    def _pick_description(props: dict) -> str:
        if not isinstance(props, dict):
            return ""
        d = props.get("Description")
        if not isinstance(d, dict):
            return ""
        # Notion DB property type "rich_text"
        if "rich_text" in d:
            return _extract_plain_text(d.get("rich_text"))
        # Defensive fallback (some DBs might misuse types)
        if "title" in d:
            return _extract_plain_text(d.get("title"))
        return ""

    def _split_legacy_title(title: str, desc: str) -> tuple[str, str]:
        """
        If desc missing, attempt:
          "Title | Description"
          "Title : Description"
        """
        t = (title or "").strip()
        d = (desc or "").strip()
        if d:
            return (t, d)

        for sep in ["|", ":"]:
            if sep in t:
                left, right = t.split(sep, 1)
                left = left.strip()
                right = right.strip()
                if left and right:
                    return (left, right)
        return (t, "")

    def _get_status_name(props: dict) -> str:
        if not isinstance(props, dict):
            return ""
        st = props.get("Status")
        if not isinstance(st, dict):
            return ""
        if isinstance(st.get("status"), dict):
            n = st["status"].get("name")
            return n if isinstance(n, str) else ""
        if isinstance(st.get("select"), dict):
            n = st["select"].get("name")
            return n if isinstance(n, str) else ""
        return ""

    def _get_due(props: dict) -> str | None:
        if not isinstance(props, dict):
            return None
        due = props.get("Due")
        if not isinstance(due, dict):
            return None
        d = due.get("date")
        if not isinstance(d, dict):
            return None
        start = d.get("start")
        if not isinstance(start, str) or not start:
            return None
        return start[:10]

    def _is_done_like(status_name: str) -> bool:
        s = (status_name or "").strip().lower()
        if not s:
            return False
        if s in {"done", "completed", "complete"}:
            return True
        if "done" in s or "completed" in s or "complete" in s:
            return True
        return False

    def _query(payload: dict):
        return requests.request(
            "POST",
            f"https://api.notion.com/v1/databases/{tasks_db_id}/query",
            headers=headers,
            json=payload,
            timeout=30,
        )

    payload_status = {
        "page_size": 50,
        "sorts": [{"property": "Due", "direction": "ascending"}],
        "filter": {
            "and": [
                {"property": "Status", "status": {"does_not_equal": "done"}},
                {"property": "Status", "status": {"does_not_equal": "Done"}},
            ]
        },
    }

    r = _query(payload_status)

    if r.status_code == 400:
        payload_select = {
            "page_size": 50,
            "sorts": [{"property": "Due", "direction": "ascending"}],
            "filter": {
                "and": [
                    {"property": "Status", "select": {"does_not_equal": "done"}},
                    {"property": "Status", "select": {"does_not_equal": "Done"}},
                ]
            },
        }
        r2 = _query(payload_select)
        if r2.status_code != 200:
            snippet2 = (getattr(r2, "text", "") or "")[:500]
            snippet1 = (getattr(r, "text", "") or "")[:500]
            raise RuntimeError(f"Notion query failed (status->select retry failed). {snippet1} / {snippet2}")
        r = r2

    if r.status_code != 200:
        snippet = (getattr(r, "text", "") or "")[:500]
        raise RuntimeError(f"Notion query failed. HTTP {r.status_code}: {snippet}")

    data = r.json() or {}
    results = data.get("results") or []

    out: list[dict] = []
    for page in results:
        if not isinstance(page, dict):
            continue
        pid = page.get("id")
        props = page.get("properties") or {}
        if not isinstance(pid, str) or not pid:
            continue

        title_raw = _pick_title(props).strip()
        desc_raw = _pick_description(props).strip()
        title_norm, desc_norm = _split_legacy_title(title_raw, desc_raw)

        status_name = _get_status_name(props).strip()
        due = _get_due(props)

        if _is_done_like(status_name):
            continue

        out.append(
            {
                "id": pid,
                "title": title_norm or "(untitled)",
                "description": desc_norm or "",
                "due": due,
                "status": status_name or None,
            }
        )

    return out[:limit_i]

def list_unique_task_titles(tasks_db_id: str, *, limit: int = 20) -> list[str]:
    """
    Fetch unique Titles from the Tasks DB (sorted alphabetically).

    Notes:
    - Notion doesn't support DISTINCT, so we paginate and dedupe client-side.
    - Dedupe is case-insensitive ("Work" and "work" collapse).
    - We do NOT filter by status: you want category reuse even if tasks are done.
    - Stops when we collected `limit` unique non-empty titles.
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

    limit_i = int(limit or 20)
    if limit_i < 1:
        limit_i = 1

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": notion_version,
        "Content-Type": "application/json",
    }

    def _extract_plain_text(rich_list) -> str:
        if not isinstance(rich_list, list):
            return ""
        parts = []
        for seg in rich_list:
            if not isinstance(seg, dict):
                continue
            pt = seg.get("plain_text")
            if isinstance(pt, str) and pt:
                parts.append(pt)
                continue
            txt = seg.get("text") or {}
            if isinstance(txt, dict):
                c = txt.get("content")
                if isinstance(c, str) and c:
                    parts.append(c)
        return "".join(parts).strip()

    def _pick_title(props: dict) -> str:
        if not isinstance(props, dict):
            return ""
        t = props.get("Title")
        if isinstance(t, dict):
            if "title" in t:
                return _extract_plain_text(t.get("title"))
            if "rich_text" in t:
                return _extract_plain_text(t.get("rich_text"))
        n = props.get("Name")
        if isinstance(n, dict):
            if "title" in n:
                return _extract_plain_text(n.get("title"))
            if "rich_text" in n:
                return _extract_plain_text(n.get("rich_text"))
        for v in props.values():
            if isinstance(v, dict) and "title" in v:
                s = _extract_plain_text(v.get("title"))
                if s:
                    return s
        return ""

    # key = casefold(title), value = first-seen original casing
    titles_by_key: dict[str, str] = {}
    cursor: str | None = None

    for _ in range(10):  # safety cap
        payload: dict = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor

        r = requests.request(
            "POST",
            f"https://api.notion.com/v1/databases/{tasks_db_id}/query",
            headers=headers,
            json=payload,
            timeout=30,
        )
        if r.status_code != 200:
            snippet = (getattr(r, "text", "") or "")[:500]
            raise RuntimeError(f"Notion query failed. HTTP {r.status_code}: {snippet}")

        data = r.json() or {}
        results = data.get("results") or []

        for page in results:
            if not isinstance(page, dict):
                continue
            props = page.get("properties") or {}
            title = _pick_title(props).strip()
            if not title:
                continue

            # Backward compat: if old format "Title | Desc" or "Title : Desc",
            # keep only the left Title for dedupe
            for sep in ["|", ":"]:
                if sep in title:
                    left = title.split(sep, 1)[0].strip()
                    if left:
                        title = left
                    break

            key = title.casefold()
            if key and key not in titles_by_key:
                titles_by_key[key] = title

            if len(titles_by_key) >= limit_i:
                break

        if len(titles_by_key) >= limit_i:
            break

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    keys_sorted = sorted(titles_by_key.keys())
    return [titles_by_key[k] for k in keys_sorted][:limit_i]




def mark_task_done(page_id: str) -> bool:
    """
    Mark a task as done in Notion.

    Hard requirements:
    - Sanitizes NOTION_TOKEN (Secret Manager sometimes adds newline).
    - Pinned Notion-Version default to 2022-06-28.
    - Works whether Status is a Notion `status` property OR a `select`.
    - Works whether the done option is "done", "Done", "✅ Done", etc.
    - First try includes Completed At; if Notion says the property doesn't exist, retry without it.
    - Tries kind fallback (status -> select) before trying alternate done names.
    - Default first attempt uses name "done" when schema isn't available (keeps your older tests happy).
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

    tasks_db_id = (os.getenv("NOTION_TASKS_DB_ID") or "").strip()

    discovered_kind: str | None = None  # "status" or "select"
    discovered_done_name: str | None = None
    completed_at_supported: bool | None = None  # None = unknown

    # Best-effort schema discovery (only if Tasks DB ID is configured)
    if tasks_db_id:
        try:
            rdb = requests.request(
                "GET",
                f"https://api.notion.com/v1/databases/{tasks_db_id}",
                headers=headers,
                timeout=30,
            )
            if rdb.status_code == 200:
                db = rdb.json() or {}
                props = (db.get("properties") or {}) if isinstance(db, dict) else {}

                status_prop = props.get("Status") if isinstance(props, dict) else None
                if isinstance(status_prop, dict):
                    ptype = status_prop.get("type")
                    if ptype in {"status", "select"}:
                        discovered_kind = ptype

                    options = []
                    if ptype == "status":
                        options = ((status_prop.get("status") or {}).get("options") or [])
                    elif ptype == "select":
                        options = ((status_prop.get("select") or {}).get("options") or [])

                    names: list[str] = []
                    for opt in options:
                        if isinstance(opt, dict) and isinstance(opt.get("name"), str):
                            nm = opt["name"].strip()
                            if nm:
                                names.append(nm)

                    # Prefer exact "done" match, then other common variants
                    for c in ["done", "Done", "✅ Done", "Completed", "complete", "Complete"]:
                        if c in names:
                            discovered_done_name = c
                            break

                    # fallback by normalization if not found
                    if not discovered_done_name:
                        for n in names:
                            lo = n.lower()
                            if lo in {"done", "completed", "complete"} or ("done" in lo) or ("complete" in lo):
                                discovered_done_name = n
                                break

                # Completed At property existence (if present and is date)
                ca = props.get("Completed At") if isinstance(props, dict) else None
                if isinstance(ca, dict):
                    completed_at_supported = (ca.get("type") == "date")
                else:
                    completed_at_supported = False
        except Exception:
            discovered_kind = None
            discovered_done_name = None
            completed_at_supported = None

    # Default done name must be lowercase "done" first if schema didn't give us a better one
    primary_done = (discovered_done_name or "done").strip() or "done"

    done_name_candidates: list[str] = []
    for x in [primary_done, "done", "Done", "✅ Done", "Completed", "complete", "Complete"]:
        x = (x or "").strip()
        if x and x not in done_name_candidates:
            done_name_candidates.append(x)

    # Prefer DB kind first if known
    if discovered_kind in {"status", "select"}:
        kinds = [discovered_kind, "select" if discovered_kind == "status" else "status"]
    else:
        kinds = ["status", "select"]

    # Completed At try order:
    if completed_at_supported is True:
        include_orders = [True, False]
    elif completed_at_supported is False:
        include_orders = [False]
    else:
        include_orders = [True, False]

    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    def _patch(props: dict) -> requests.Response:
        return requests.request(
            "PATCH",
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=headers,
            json={"properties": props},
            timeout=30,
        )

    # Loop order matters for your tests:
    # name -> kind -> include_completed
    # so for name="done": status+completed, status only, select+completed, select only
    for name in done_name_candidates:
        for kind in kinds:
            for include_completed in include_orders:
                props: dict = {"Status": {kind: {"name": name}}}
                if include_completed:
                    props["Completed At"] = {"date": {"start": now_iso}}

                r = _patch(props)
                if r.status_code in (200, 201):
                    return True
                if r.status_code == 404:
                    return False

                txt = (getattr(r, "text", "") or "")
                # If Completed At missing, next attempt should naturally omit it
                if include_completed and ("Completed At" in txt) and (
                    ("does not exist" in txt) or ("is not a property" in txt)
                ):
                    continue

    return False


def list_inbox_tasks(tasks_db_id: str, *, limit: int = 20) -> list[dict]:
    """
    Inbox view: open tasks (Status != done), sorted by Due asc.
    Returns simplified list: [{"id": page_id, "title": "...", "status": "...", "due": "..."}]
    """
    # Reuse list_open_tasks logic but with a larger default limit.
    return list_open_tasks(tasks_db_id, limit=limit)



def update_task_title(task_page_id: str, title: str) -> bool:
    """
    Update a task's Title in Notion.

    Tries "Title" first, then falls back to "Name" if the DB uses a different title property.
    """
    import os
    import requests

    raw_token = os.getenv("NOTION_TOKEN") or ""
    token = raw_token.strip().replace("\r", "").replace("\n", "")
    if not token:
        raise RuntimeError("NOTION_TOKEN is not set")

    notion_version = (os.getenv("NOTION_VERSION") or "2022-06-28").strip() or "2022-06-28"

    task_page_id = (task_page_id or "").strip()
    if not task_page_id:
        raise ValueError("task_page_id is required")

    title = (title or "").strip()
    if not title:
        raise ValueError("title is required")

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": notion_version,
        "Content-Type": "application/json",
    }

    def _patch(prop_name: str):
        payload = {
            "properties": {
                prop_name: {"title": [{"type": "text", "text": {"content": title}}]}
            }
        }
        return requests.request(
            "PATCH",
            f"https://api.notion.com/v1/pages/{task_page_id}",
            headers=headers,
            json=payload,
            timeout=30,
        )

    r1 = _patch("Title")
    if r1.status_code in (200, 201):
        return True

    # fallback if "Title" isn't a property in this DB
    if r1.status_code == 400:
        r2 = _patch("Name")
        if r2.status_code in (200, 201):
            return True

    return False


def update_task_description(task_page_id: str, description: str) -> bool:
    """
    Update a task's Description (rich_text) in Notion.

    - Uses property name "Description" first.
    - If the DB uses a different name, falls back to "Details" on 400.
    - Allows clearing: empty/whitespace description => rich_text: []
    """
    import os
    import requests

    raw_token = os.getenv("NOTION_TOKEN") or ""
    token = raw_token.strip().replace("\r", "").replace("\n", "")
    if not token:
        raise RuntimeError("NOTION_TOKEN is not set")

    notion_version = (os.getenv("NOTION_VERSION") or "2022-06-28").strip() or "2022-06-28"

    task_page_id = (task_page_id or "").strip()
    if not task_page_id:
        raise ValueError("task_page_id is required")

    # NOTE: empty is allowed (means clear)
    desc = "" if description is None else str(description)

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": notion_version,
        "Content-Type": "application/json",
    }

    def _payload(prop_name: str) -> dict:
        cleaned = desc.strip()
        if cleaned:
            rich_text = [{"type": "text", "text": {"content": cleaned}}]
        else:
            # Clear the property
            rich_text = []
        return {"properties": {prop_name: {"rich_text": rich_text}}}

    def _patch(prop_name: str):
        return requests.request(
            "PATCH",
            f"https://api.notion.com/v1/pages/{task_page_id}",
            headers=headers,
            json=_payload(prop_name),
            timeout=30,
        )

    r1 = _patch("Description")
    if r1.status_code in (200, 201):
        return True

    # fallback if "Description" isn't a property in this DB
    if r1.status_code == 400:
        r2 = _patch("Details")
        if r2.status_code in (200, 201):
            return True

    return False
