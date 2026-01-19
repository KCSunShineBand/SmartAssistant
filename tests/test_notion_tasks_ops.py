import notion


class FakeResp:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = "" if payload is None else str(payload)
        self.content = b"1"

    def json(self):
        return self._payload


def test_list_open_tasks_queries_db(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    calls = []

    def fake_request(method, url, headers=None, json=None, timeout=None):
        calls.append((method, url, json))
        assert method == "POST"
        assert url.endswith("/v1/databases/tasksdb/query")
        return FakeResp(
            200,
            {
                "results": [
                    {
                        "id": "p1",
                        "properties": {
                            "Title": {"title": [{"plain_text": "Buy milk"}]},
                            "Status": {"select": {"name": "todo"}},
                            "Due": {"date": {"start": "2026-01-20"}},
                        },
                    }
                ]
            },
        )

    monkeypatch.setattr("requests.request", fake_request)
    out = notion.list_open_tasks("tasksdb", limit=5)
    assert out[0]["id"] == "p1"
    assert out[0]["title"] == "Buy milk"
    assert out[0]["status"] == "todo"
    assert out[0]["due"] == "2026-01-20"
    assert calls[0][2]["filter"]["and"][0]["property"] == "Status"


def test_mark_task_done_patches_page(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    calls = []

    def fake_request(method, url, headers=None, json=None, timeout=None):
        calls.append((method, url, json))
        assert method == "PATCH"
        assert url.endswith("/v1/pages/p1")
        # Status is a Notion `status` property (NOT select)
        assert json["properties"]["Status"]["status"]["name"] == "done"
        assert "Completed At" in json["properties"]
        assert "start" in json["properties"]["Completed At"]["date"]
        return FakeResp(200, {"id": "p1"})

    monkeypatch.setattr("requests.request", fake_request)
    assert notion.mark_task_done("p1") is True
    assert len(calls) == 1
