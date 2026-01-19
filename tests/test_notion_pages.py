import notion


class FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = "" if payload is None else str(payload)
        self.content = b"1"

    def json(self):
        return self._payload


def test_create_note_requires_token(monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    try:
        notion.create_note("db", title="t", text="x")
        assert False, "Expected RuntimeError"
    except RuntimeError as e:
        assert "NOTION_TOKEN" in str(e)


def test_create_note_payload_and_chunking(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "test-token")
    monkeypatch.setenv("NOTION_VERSION", "2025-09-03")  # should be ignored; we pin in code

    calls = []

    def fake_request(method, url, headers=None, json=None, timeout=None):
        calls.append((method, url, headers or {}, json))
        assert method == "POST"
        assert url.endswith("/v1/pages")

        # Code must pin version regardless of env
        assert (headers or {}).get("Notion-Version") == "2022-06-28"
        return FakeResp(200, {"id": "note-page-123"})

    monkeypatch.setattr("requests.request", fake_request)

    long_text = "A" * 4200  # should chunk into multiple rich_text items
    pid = notion.create_note(
        "notes-db-1",
        title="Hello",
        text=long_text,
        note_type="other",  # ignored (no such property in live DB)
        tags=["t1", "t2"],  # ignored
        labels=["Personal"],
        telegram_message_link="https://example.com/msg",  # appended into Body text
    )

    assert pid == "note-page-123"
    assert len(calls) == 1

    payload = calls[0][3]
    assert payload["parent"]["database_id"] == "notes-db-1"

    props = payload["properties"]
    # Live schema only
    assert set(props.keys()) == {"Title", "Body", "Labels", "Source"}

    assert props["Title"]["title"][0]["text"]["content"] == "Hello"
    assert props["Labels"]["multi_select"] == [{"name": "Personal"}]
    assert props["Source"]["select"]["name"] == "telegram"

    # Body is rich_text and should be chunked
    rt = props["Body"]["rich_text"]
    assert isinstance(rt, list)
    assert len(rt) > 1  # 4200 chars should chunk

    combined = "".join(x["text"]["content"] for x in rt)
    assert long_text in combined
    assert "Telegram: https://example.com/msg" in combined


def test_create_task_payload(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "test-token")
    monkeypatch.setenv("NOTION_VERSION", "2025-09-03")

    calls = []

    def fake_request(method, url, headers=None, json=None, timeout=None):
        calls.append((method, url, headers or {}, json))
        return FakeResp(200, {"id": "task-page-999"})

    monkeypatch.setattr("requests.request", fake_request)

    pid = notion.create_task(
        "tasks-db-1",
        title="Buy milk",
        status="todo",
        due="2026-01-20",
        priority="med",
        labels=["Personal", "Admin"],
        source_note_page_ids=["note-page-123"],
    )

    assert pid == "task-page-999"
    payload = calls[0][3]
    assert payload["parent"]["database_id"] == "tasks-db-1"
    assert payload["properties"]["Title"]["title"][0]["text"]["content"] == "Buy milk"
    assert payload["properties"]["Due"]["date"]["start"] == "2026-01-20"
    assert payload["properties"]["Source Notes"]["relation"][0]["id"] == "note-page-123"
