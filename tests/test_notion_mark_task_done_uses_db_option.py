import os
import notion


class FakeResp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data


def test_mark_task_done_uses_existing_done_option(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "t")
    monkeypatch.setenv("NOTION_VERSION", "2022-06-28")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "tasks_db")

    calls = {"patch_payloads": []}

    def fake_request(method, url, headers=None, json=None, timeout=None):
        # DB schema lookup: returns Status options including "✅ Done"
        if method == "GET" and "/v1/databases/tasks_db" in url:
            return FakeResp(
                200,
                json_data={
                    "properties": {
                        "Status": {
                            "type": "status",
                            "status": {
                                "options": [{"name": "Doing"}, {"name": "✅ Done"}]
                            },
                        }
                    }
                },
            )

        # Page PATCH: only succeed if the code uses "✅ Done"
        if method == "PATCH" and "/v1/pages/" in url:
            calls["patch_payloads"].append(json or {})
            props = (json or {}).get("properties") or {}
            st = props.get("Status") or {}
            # allow either status or select payload kind
            name = None
            if "status" in st:
                name = (st.get("status") or {}).get("name")
            elif "select" in st:
                name = (st.get("select") or {}).get("name")

            if name == "✅ Done":
                return FakeResp(200, json_data={})
            return FakeResp(400, json_data={}, text="invalid option")

        return FakeResp(500, json_data={}, text="unexpected call")

    import requests
    monkeypatch.setattr(requests, "request", fake_request)

    assert notion.mark_task_done("page_123") is True
    assert calls["patch_payloads"], "Expected at least one PATCH attempt"
