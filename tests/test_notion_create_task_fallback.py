import requests
import notion


class _Resp:
    def __init__(self, status_code: int, json_data=None, text: str = ""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        return self._json


def test_create_task_falls_back_to_select_when_status_rejected(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret")

    calls = []

    def fake_request(method, url, headers=None, json=None, timeout=None):
        assert method == "POST"
        assert url.endswith("/v1/pages")
        calls.append(json)

        # 1st call uses status -> reject
        if len(calls) == 1:
            assert "Status" in json["properties"]
            assert "status" in json["properties"]["Status"]
            return _Resp(400, text="body failed validation: expected select")

        # 2nd call uses select -> ok
        assert "select" in json["properties"]["Status"]
        return _Resp(200, json_data={"id": "task_1"})

    monkeypatch.setattr(requests, "request", fake_request)

    out = notion.create_task("db_123", title="Do something")
    assert out == "task_1"
    assert len(calls) == 2


def test_create_task_uses_status_filter_when_supported(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret")

    calls = []

    def fake_request(method, url, headers=None, json=None, timeout=None):
        calls.append(json)
        return _Resp(200, json_data={"id": "task_2"})

    monkeypatch.setattr(requests, "request", fake_request)

    out = notion.create_task("db_456", title="Write report")
    assert out == "task_2"
    assert len(calls) == 1
    assert "status" in calls[0]["properties"]["Status"]
