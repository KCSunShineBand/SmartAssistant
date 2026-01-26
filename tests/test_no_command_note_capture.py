from core import AppState, handle_event


def test_slash_text_is_not_saved_as_note_when_routed_as_text():
    state = AppState()
    chat_id = 123

    # Force it to be treated as plain text
    actions = handle_event(
        {
            "type": "message",
            "chat_id": chat_id,
            "user_id": 999,
            "message_id": 1,
            "text": "/definitely_not_a_real_command",
            "route": {"kind": "text", "text": "/definitely_not_a_real_command"},
        },
        state,
    )

    assert actions and actions[0]["type"] == "reply"
    assert "Unknown command" in actions[0]["text"]

    # Ensure no note was created in memory fallback
    assert state.notes.get(chat_id, []) == []
