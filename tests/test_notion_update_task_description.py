import os
import notion


class DummyResp:
    def __init__(self, status_code: int):
        self.status_code = status_code


def test_update_task_description_sets_rich_text(monkeypatch):
    os.environ["NOTION_TOKEN"] = "tok\n"  # include newline to ensure sanitization

    seen = {}

    import requests

    def fake_request(method, url, headers=None, json=None, timeout=None):
        seen["method"] = method
        seen["url"] = url
        seen["headers"] = headers
        seen["json"] = json
        return DummyResp(200)

    monkeypatch.setattr(requests, "request", fake_request)

    ok = notion.update_task_description("page123", "Hello world")
    assert ok is True
    assert seen["method"] == "PATCH"
    assert "Authorization" in seen["headers"]
    # Should write Description rich_text with content
    assert seen["json"]["properties"]["Description"]["rich_text"][0]["text"]["content"] == "Hello world"


def test_update_task_description_clears_when_empty(monkeypatch):
    os.environ["NOTION_TOKEN"] = "tok"

    import requests

    def fake_request(method, url, headers=None, json=None, timeout=None):
        return DummyResp(200)

    monkeypatch.setattr(requests, "request", fake_request)

    ok = notion.update_task_description("page123", "   ")
    assert ok is True


def test_update_task_description_fallback_to_details(monkeypatch):
    os.environ["NOTION_TOKEN"] = "tok"

    calls = []

    import requests

    def fake_request(method, url, headers=None, json=None, timeout=None):
        # First call (Description) fails with 400, second (Details) succeeds
        calls.append(json)
        return DummyResp(400 if len(calls) == 1 else 200)

    monkeypatch.setattr(requests, "request", fake_request)

    ok = notion.update_task_description("page123", "X")
    assert ok is True
    assert "Description" in calls[0]["properties"]
    assert "Details" in calls[1]["properties"]
