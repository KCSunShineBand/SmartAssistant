import main


def test_normalize_update_includes_callback_id_and_message_id():
    update = {
        "update_id": 123,
        "callback_query": {
            "id": "cbq_abc123",
            "from": {"id": 9},
            "data": "today|x=1",
            "message": {
                "message_id": 77,
                "chat": {"id": 555},
                "text": "irrelevant",
            },
        },
    }

    ev = main.normalize_update(update)

    assert ev["type"] == "callback"
    assert ev["chat_id"] == 555
    assert ev["user_id"] == 9
    assert ev["message_id"] == 77
    assert ev["callback_id"] == "cbq_abc123"
    assert ev["data"] == "today|x=1"
    assert ev["callback"]["action"] == "today"
    assert ev["callback"]["params"]["x"] == "1"
