import notion


class FakeResp:
    def __init__(self, status_code=200, body=None, text=""):
        self.status_code = status_code
        self._body = body or {}
        self.text = text
        self.content = b"{}"

    def json(self):
        return self._body


def test_mark_task_done_sanitizes_token_and_pins_version(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "abc\n")  # includes newline to prove sanitization

    calls = []

    def fake_request(method, url, headers=None, json=None, timeout=None):
        calls.append((method, url, headers or {}, json or {}))
        return FakeResp(200, {"ok": True})

    monkeypatch.setattr("requests.request", fake_request)

    assert notion.mark_task_done("page_1") is True
    assert len(calls) == 1

    method, url, headers, payload = calls[0]
    assert method == "PATCH"
    assert url.endswith("/v1/pages/page_1")
    assert headers["Authorization"] == "Bearer abc"
    assert headers["Notion-Version"] == "2022-06-28"

    # First attempt includes Completed At
    assert payload["properties"]["Status"]["status"]["name"] == "done"
    assert "Completed At" in payload["properties"]


def test_mark_task_done_falls_back_if_completed_at_missing(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "abc\n")

    calls = []

    def fake_request(method, url, headers=None, json=None, timeout=None):
        calls.append((method, url, headers or {}, json or {}))
        # First call fails because Completed At doesn't exist
        if len(calls) == 1:
            return FakeResp(400, text="Completed At is not a property that exists.")
        # Second call succeeds
        return FakeResp(200, {"ok": True})

    monkeypatch.setattr("requests.request", fake_request)

    assert notion.mark_task_done("page_1") is True
    assert len(calls) == 2

    # First payload had Completed At
    assert "Completed At" in calls[0][3]["properties"]
    # Second payload should NOT have it
    assert "Completed At" not in calls[1][3]["properties"]
    assert calls[1][3]["properties"]["Status"]["status"]["name"] == "done"
