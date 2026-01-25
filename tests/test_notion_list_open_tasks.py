import notion


class FakeResp:
    def __init__(self, status_code=200, body=None, text=""):
        self.status_code = status_code
        self._body = body or {}
        self.text = text
        self.content = b"{}"

    def json(self):
        return self._body


def test_list_open_tasks_uses_status_filter_and_parses_status(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "abc\n")  # prove CR/LF sanitized

    captured = {}

    def fake_request(method, url, headers=None, json=None, timeout=None):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers or {}
        captured["json"] = json or {}
        captured["timeout"] = timeout

        return FakeResp(
            200,
            {
                "results": [
                    {
                        "id": "task_1",
                        "properties": {
                            "Title": {"title": [{"plain_text": "Do the thing"}]},
                            "Status": {"status": {"name": "todo"}},
                            "Due": {"date": {"start": "2026-01-20"}},
                        },
                    }
                ]
            },
        )

    monkeypatch.setattr("requests.request", fake_request)

    out = notion.list_open_tasks("db_1", limit=5)

    # Request assertions
    assert captured["method"] == "POST"
    assert "/v1/databases/db_1/query" in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer abc"
    assert captured["headers"]["Notion-Version"] == "2022-06-28"

    # Filter must be status-type (not select-type)
    f = captured["json"]["filter"]["and"]
    assert any("status" in cond for cond in f)
    assert all("select" not in cond for cond in f)

    # Response parsing
    assert out == [{"id": "task_1", "title": "Do the thing", "description": "", "status": "todo", "due": "2026-01-20"}]
