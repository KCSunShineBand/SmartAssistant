import os
import notion
import requests


class _Resp:
    def __init__(self, code=200, json_data=None, text=""):
        self.status_code = code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


def test_create_task_includes_description_rich_text(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_VERSION", "2022-06-28")

    captured = {}

    def fake_request(method, url, headers=None, json=None, timeout=None):
        assert method == "POST"
        assert url.endswith("/v1/pages")
        captured["payload"] = json
        return _Resp(200, {"id": "page_1"})

    monkeypatch.setattr(requests, "request", fake_request)

    pid = notion.create_task(
        "tasksdb",
        title="Grocery",
        description="Buy milk",
        status="todo",
        due=None,
        priority="med",
        labels=[],
        source="telegram",
        source_note_page_ids=None,
    )

    assert pid == "page_1"
    props = captured["payload"]["properties"]
    assert props["Title"]["title"][0]["text"]["content"] == "Grocery"
    assert props["Description"]["rich_text"][0]["text"]["content"] == "Buy milk"


def test_list_open_tasks_returns_description(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_VERSION", "2022-06-28")

    def fake_request(method, url, headers=None, json=None, timeout=None):
        assert method == "POST"
        assert "/v1/databases/" in url and url.endswith("/query")
        return _Resp(
            200,
            {
                "results": [
                    {
                        "id": "p1",
                        "properties": {
                            "Title": {"title": [{"plain_text": "Grocery"}]},
                            "Description": {"rich_text": [{"plain_text": "Buy milk"}]},
                            "Status": {"select": {"name": "todo"}},
                            "Due": {"date": None},
                        },
                    }
                ]
            },
        )

    monkeypatch.setattr(requests, "request", fake_request)

    out = notion.list_open_tasks("tasksdb", limit=5)
    assert out[0]["id"] == "p1"
    assert out[0]["title"] == "Grocery"
    assert out[0]["description"] == "Buy milk"


def test_list_unique_task_titles_dedupes_and_sorts(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_VERSION", "2022-06-28")

    calls = {"n": 0}

    def fake_request(method, url, headers=None, json=None, timeout=None):
        calls["n"] += 1
        assert method == "POST"
        assert url.endswith("/query")

        # Page 1
        if calls["n"] == 1:
            return _Resp(
                200,
                {
                    "results": [
                        {"properties": {"Title": {"title": [{"plain_text": "Work"}]}}},
                        {"properties": {"Title": {"title": [{"plain_text": "Grocery"}]}}},
                        # legacy format should be normalized to "Grocery"
                        {"properties": {"Title": {"title": [{"plain_text": "Grocery | Buy Eggs"}]}}},
                    ],
                    "has_more": True,
                    "next_cursor": "c2",
                },
            )

        # Page 2
        return _Resp(
            200,
            {
                "results": [
                    {"properties": {"Title": {"title": [{"plain_text": "Bills"}]}}},
                    {"properties": {"Title": {"title": [{"plain_text": "work"}]}}},  # case variant
                ],
                "has_more": False,
                "next_cursor": None,
            },
        )

    monkeypatch.setattr(requests, "request", fake_request)

    titles = notion.list_unique_task_titles("tasksdb", limit=20)
    assert titles == ["Bills", "Grocery", "Work"]

