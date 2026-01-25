import os
import notion

class FakeResp:
    def __init__(self, status_code=200, data=None, text=""):
        self.status_code = status_code
        self._data = data or {}
        self.text = text

    def json(self):
        return self._data


def test_list_open_tasks_joins_title_and_filters_done_like(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")

    calls = {"n": 0}

    def fake_request(method, url, headers=None, json=None, timeout=None):
        calls["n"] += 1

        # DB schema discovery
        if method == "GET" and "/v1/databases/" in url and not url.endswith("/query"):
            return FakeResp(
                200,
                data={
                    "properties": {
                        "Status": {
                            "status": {
                                "options": [
                                    {"name": "Todo"},
                                    {"name": "Doing"},
                                    {"name": "Completed"},
                                ]
                            }
                        }
                    }
                },
            )

        # Query
        if method == "POST" and url.endswith("/query"):
            return FakeResp(
                200,
                data={
                    "results": [
                        {
                            "id": "p1",
                            "properties": {
                                "Title": {"title": [{"plain_text": "buy"}, {"plain_text": " milk"}]},
                                "Status": {"status": {"name": "Todo"}},
                                "Due": {"date": {"start": "2026-01-25"}},
                            },
                        },
                        {
                            "id": "p2",
                            "properties": {
                                "Title": {"title": [{"plain_text": "old task"}]},
                                "Status": {"status": {"name": "Completed"}},
                                "Due": {"date": None},
                            },
                        },
                        {
                            "id": "p3",
                            "properties": {
                                "Title": {"title": [{"plain_text": ""}]},
                                "Status": {"status": {"name": "Doing"}},
                                "Due": {"date": None},
                            },
                        },
                    ]
                },
            )

        return FakeResp(404, text="unexpected call")

    import requests
    monkeypatch.setattr(requests, "request", fake_request)

    out = notion.list_open_tasks("db123", limit=10)
    assert [x["id"] for x in out] == ["p1", "p3"]          # p2 filtered out (Completed)
    assert out[0]["title"] == "buy milk"                   # joined
    assert out[1]["title"] == "(untitled)"                 # fallback
