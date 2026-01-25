import requests
import notion


class _Resp:
    def __init__(self, status_code: int, json_data=None, text: str = ""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


def test_list_open_tasks_falls_back_to_select_filter(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret")

    calls = []

    def fake_request(method, url, headers=None, json=None, timeout=None):
        assert method == "POST"
        assert "/v1/databases/" in url and url.endswith("/query")
        calls.append(json)

        # 1st call: status filter -> Notion rejects it (pretend DB uses select)
        if len(calls) == 1:
            assert "filter" in json
            f0 = json["filter"]["and"][0]
            assert f0["property"] == "Status"
            assert "status" in f0
            return _Resp(400, text="database property Status does not match filter select")

        # 2nd call: select filter -> ok
        f0 = json["filter"]["and"][0]
        assert f0["property"] == "Status"
        assert "select" in f0
        return _Resp(
            200,
            json_data={
                "results": [
                    {
                        "id": "page_1",
                        "properties": {
                            "Title": {"title": [{"plain_text": "Pay rent"}]},
                            "Status": {"select": {"name": "todo"}},
                            "Due": {"date": {"start": "2026-01-21"}},
                        },
                    }
                ]
            },
        )

    monkeypatch.setattr(requests, "request", fake_request)

    out = notion.list_open_tasks("db_123", limit=10)

    assert len(calls) == 2
    assert out == [{"id": "page_1", "title": "Pay rent", "description": "", "status": "todo", "due": "2026-01-21"}]


def test_list_open_tasks_uses_status_filter_when_supported(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret")

    calls = []

    def fake_request(method, url, headers=None, json=None, timeout=None):
        calls.append(json)
        # status filter works immediately
        return _Resp(
            200,
            json_data={
                "results": [
                    {
                        "id": "page_2",
                        "properties": {
                            "Title": {"title": [{"plain_text": "Write report"}]},
                            "Status": {"status": {"name": "doing"}},
                            "Due": {"date": None},
                        },
                    }
                ]
            },
        )

    monkeypatch.setattr(requests, "request", fake_request)

    out = notion.list_open_tasks("db_456", limit=5)

    assert len(calls) == 1
    f0 = calls[0]["filter"]["and"][0]
    assert f0["property"] == "Status"
    assert "status" in f0
    assert out == [{"id": "page_2", "title": "Write report", "description": "", "status": "doing", "due": None}]

