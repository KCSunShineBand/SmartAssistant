import os
import notion

def test_setup_databases_requires_token(monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    try:
        notion.setup_databases("some-page-id")
        assert False, "Expected RuntimeError"
    except RuntimeError as e:
        assert "NOTION_TOKEN" in str(e)

def test_setup_databases_creates_dbs_and_relation(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "test-token")
    monkeypatch.setenv("NOTION_VERSION", "2025-09-03")

    calls = []

    class FakeResp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload
            self.text = "" if payload is None else str(payload)
            self.content = b"1"

        def json(self):
            return self._payload

    def fake_request(method, url, headers=None, json=None, timeout=None):
        calls.append((method, url, headers or {}, json))

        # Create KC Notes
        if method == "POST" and url.endswith("/v1/databases") and json["title"][0]["text"]["content"] == "KC Notes":
            return FakeResp(
                200,
                {
                    "id": "notes-db-id",
                    "data_sources": [{"id": "notes-ds-id", "name": "KC Notes"}],
                },
            )

        # Create KC Tasks
        if method == "POST" and url.endswith("/v1/databases") and json["title"][0]["text"]["content"] == "KC Tasks":
            return FakeResp(
                200,
                {
                    "id": "tasks-db-id",
                    "data_sources": [{"id": "tasks-ds-id", "name": "KC Tasks"}],
                },
            )

        # Patch relation onto tasks data source
        if method == "PATCH" and url.endswith("/v1/data_sources/tasks-ds-id"):
            return FakeResp(200, {"ok": True})

        return FakeResp(400, {"error": "unexpected call"})

    monkeypatch.setattr("requests.request", fake_request)

    out = notion.setup_databases("parent-page-id")
    assert out == {"notes_db_id": "notes-db-id", "tasks_db_id": "tasks-db-id"}

    # Sanity: 2 creates + 1 patch
    assert len(calls) == 3

    # Validate labels seeded in both DBs
    notes_create = calls[0][3]
    tasks_create = calls[1][3]

    notes_labels = [o["name"] for o in notes_create["properties"]["Labels"]["multi_select"]["options"]]
    tasks_labels = [o["name"] for o in tasks_create["properties"]["Labels"]["multi_select"]["options"]]

    assert "Personal" in notes_labels
    assert "SAFEhaven" in notes_labels
    assert notes_labels == tasks_labels

    # Validate required select options
    notes_type = [o["name"] for o in notes_create["properties"]["Type"]["select"]["options"]]
    assert notes_type == ["meeting", "research", "receipt", "tech", "personal", "other"]

    tasks_status = [o["name"] for o in tasks_create["properties"]["Status"]["select"]["options"]]
    assert tasks_status == ["todo", "doing", "done"]

    # Validate relation patch payload
    patch_payload = calls[2][3]
    rel = patch_payload["properties"]["Source Notes"]["relation"]
    assert rel["data_source_id"] == "notes-ds-id"
    assert rel["dual_property"]["synced_property_name"] == "Related Tasks"
