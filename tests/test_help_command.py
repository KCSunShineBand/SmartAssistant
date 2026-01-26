from core import AppState, handle_event


def test_help_mentions_todo_wizard_and_one_shot_format():
    state = AppState()
    actions = handle_event(
        {
            "type": "message",
            "chat_id": 123,
            "user_id": 999,
            "message_id": 1,
            "text": "/help",
            "route": {"kind": "command", "command": "help", "args": ""},
        },
        state,
    )

    assert actions and actions[0]["type"] == "reply"
    txt = actions[0]["text"]

    assert "/todo - (Notion mode) task wizard" in txt
    assert "/todo Title | Description" in txt
    assert "/today - list open tasks" in txt
