import requests
import notion


class _Resp:
    def __init__(self, status_code: int, json_data=None, text: str = ""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


def test_mark_task_done_falls_back_to_select_when_status_rejected(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret")

    calls = []

    def fake_request(method, url, headers=None, json=None, timeout=None):
        assert method == "PATCH"
        assert "/v1/pages/" in url
        calls.append(json)

        # 1) status + completed -> reject (type mismatch)
        if len(calls) == 1:
            props = json["properties"]
            assert "status" in props["Status"]
            assert "Completed At" in props
            return _Resp(400, text="body failed validation: expected select")

        # 2) status only -> reject (still mismatch)
        if len(calls) == 2:
            props = json["properties"]
            assert "status" in props["Status"]
            assert "Completed At" not in props
            return _Resp(400, text="body failed validation: expected select")

        # 3) select + completed -> success
        props = json["properties"]
        assert "select" in props["Status"]
        return _Resp(200, json_data={"id": "page_ok"})

    monkeypatch.setattr(requests, "request", fake_request)

    ok = notion.mark_task_done("page_123")
    assert ok is True
    assert len(calls) == 3


def test_mark_task_done_retries_without_completed_at_if_missing(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret")

    calls = []

    def fake_request(method, url, headers=None, json=None, timeout=None):
        calls.append(json)

        # 1) status + completed -> reject unknown property
        if len(calls) == 1:
            props = json["properties"]
            assert "status" in props["Status"]
            assert "Completed At" in props
            return _Resp(400, text="Could not find property with name Completed At")

        # 2) status only -> success
        props = json["properties"]
        assert "status" in props["Status"]
        assert "Completed At" not in props
        return _Resp(200, json_data={"id": "page_ok"})

    monkeypatch.setattr(requests, "request", fake_request)

    ok = notion.mark_task_done("page_456")
    assert ok is True
    assert len(calls) == 2
