from datetime import date
import core


def test_daily_brief_notion_sections(monkeypatch):
    # Force Notion enabled (we'll mock the API call)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("NOTION_TOKEN", "dummy")
    monkeypatch.setenv("NOTION_NOTES_DB_ID", "dummy")
    monkeypatch.setenv("NOTION_TASKS_DB_ID", "dummy")

    def fake_list_inbox_tasks(db_id, limit=50):
        assert db_id == "dummy"
        return [
            {"id": "t1", "title": "Pay bill", "due": "2026-01-18", "status": "todo"},
            {"id": "t2", "title": "Submit report", "due": "2026-01-19", "status": "todo"},
            {"id": "t3", "title": "Build feature", "due": None, "status": "doing"},
            {"id": "t4", "title": "Plan roadmap", "due": None, "status": "todo"},
        ]

    monkeypatch.setattr(core.notion, "list_inbox_tasks", fake_list_inbox_tasks)

    state = core.AppState()
    text = core.build_daily_brief_text(123, state, today=date(2026, 1, 19))

    assert "Daily Brief (2026-01-19 SGT)" in text
    assert "⏰ Overdue: 1" in text
    assert "- t1: Pay bill (due 2026-01-18)" in text
    assert "📌 Due Today: 1" in text
    assert "- t2: Submit report (due 2026-01-19)" in text
    assert "🛠️ Doing: 1" in text
    assert "- t3: Build feature" in text
    assert "📥 No Due Date / Next Up: 1" in text
    assert "- t4: Plan roadmap" in text


def test_daily_brief_in_memory_fallback(monkeypatch):
    # Notion off, DB off
    for k in ["DATABASE_URL", "NOTION_TOKEN", "NOTION_NOTES_DB_ID", "NOTION_TASKS_DB_ID"]:
        monkeypatch.delenv(k, raising=False)

    state = core.AppState()
    state.tasks[999] = [
        core.Task(id="task_1", text="alpha", created_at="2026-01-01T00:00:00Z", done=False),
        core.Task(id="task_2", text="beta", created_at="2026-01-01T00:00:00Z", done=True),
    ]

    text = core.build_daily_brief_text(999, state, today=date(2026, 1, 19))
    assert "Open tasks: 1" in text
    assert "- task_1: alpha" in text
    assert "Tip: connect Notion" in text
