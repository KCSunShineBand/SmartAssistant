import os
import notion


class _FakeResp:
    def __init__(self, status_code=201, body=None, text=""):
        self.status_code = status_code
        self._body = body or {"id": "page_123"}
        self.text = text
        self.content = b"{}"

    def json(self):
        return self._body


def test_create_note_payload_matches_live_notes_schema(monkeypatch):
    # Arrange env
    monkeypatch.setenv("NOTION_TOKEN", "abc\n")  # include newline to prove sanitization
    monkeypatch.delenv("NOTION_VERSION", raising=False)  # default should be 2022-06-28

    calls = {}

    def fake_request(method, url, headers=None, json=None, timeout=None):
        calls["method"] = method
        calls["url"] = url
        calls["headers"] = headers or {}
        calls["json"] = json or {}
        calls["timeout"] = timeout
        return _FakeResp(201, {"id": "page_123"})

    monkeypatch.setattr("requests.request", fake_request)

    # Act
    page_id = notion.create_note(
        "notes_db_1",
        title="Hello",
        text="Line1\nLine2",
        labels=["Personal"],
        source="telegram",
        # these must be ignored (DB doesn't have these properties)
        note_type="tech",
        tags=["x"],
        telegram_message_link="https://t.me/c/1/2",
    )

    # Assert response
    assert page_id == "page_123"

    # Assert headers sanitized + version pinned
    assert calls["headers"]["Authorization"] == "Bearer abc"
    assert calls["headers"]["Notion-Version"] == "2022-06-28"

    # Assert payload properties ONLY use live schema keys
    props = calls["json"]["properties"]
    assert set(props.keys()) == {"Title", "Body", "Labels", "Source"}

    assert "Title" in props and "title" in props["Title"]
    assert "Body" in props and "rich_text" in props["Body"]
    assert props["Labels"]["multi_select"] == [{"name": "Personal"}]
    assert props["Source"]["select"]["name"] == "telegram"
