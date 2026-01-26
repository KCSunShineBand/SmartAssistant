from core import AppState, handle_event


def test_edit_prompt_mentions_pipe_format():
    state = AppState()
    chat_id = 123

    # Seed a cached list so edit flow can proceed
    list_mid = 99
    state.render_cache[(chat_id, list_mid)] = {
        "list_kind": "today",
        "tasks": [{"id": "t1", "title": "A", "description": "B"}],
        "text": "Open tasks: 1\n1. A | B",
    }

    # Step 1: user taps Edit (callback)
    actions = handle_event(
        {
            "type": "callback",
            "chat_id": chat_id,
            "message_id": list_mid,
            "callback": {"action": "pick_edit", "params": {}},
        },
        state,
    )
    assert actions[0]["type"] == "reply"
    assert "Which item number" in actions[0]["text"]

    # Step 2: user replies with item number "1"
    actions2 = handle_event(
        {
            "type": "message",
            "chat_id": chat_id,
            "message_id": 2,
            "user_id": 999,
            "text": "1",
            "route": {"kind": "text", "text": "1"},
        },
        state,
    )

    assert actions2[0]["type"] == "reply"
    txt = actions2[0]["text"]
    assert "New Title | New Description" in txt
    assert "| New Description" in txt
