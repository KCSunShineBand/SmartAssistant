from core import AppState, handle_event
from ui import route_text


def test_route_text_cancel():
    r = route_text("/cancel")
    assert r["kind"] == "command"
    assert r["command"] == "cancel"


def test_cancel_clears_wizard_and_pending():
    state = AppState()
    chat_id = 123

    # simulate active wizard + pending flow
    state.todo_wizard[chat_id] = {"stage": "pick_title", "titles": ["Work"]}
    state.pending[chat_id] = {"mode": "done_pick", "source_message_id": 99}

    actions = handle_event(
        {
            "type": "message",
            "chat_id": chat_id,
            "user_id": 999,
            "message_id": 1,
            "text": "/cancel",
            "route": {"kind": "command", "command": "cancel", "args": ""},
        },
        state,
    )

    assert chat_id not in state.todo_wizard
    assert chat_id not in state.pending
    assert actions and actions[0]["type"] == "reply"
    assert "Cancelled" in actions[0]["text"]
