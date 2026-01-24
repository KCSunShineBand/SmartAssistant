import main
import requests


class _Resp:
    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True}


def test_send_telegram_message_includes_reply_markup(monkeypatch):
    captured = {}

    # Avoid needing TELEGRAM_BOT_TOKEN / real URL logic
    monkeypatch.setattr(main, "_tg_api_url", lambda method: "https://example.com/sendMessage")

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["payload"] = json
        return _Resp()

    monkeypatch.setattr(requests, "post", fake_post)

    rm = {"inline_keyboard": [[{"text": "Open", "url": "https://example.com"}]]}

    main.send_telegram_message(
        123,
        "hello",
        reply_markup=rm,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )

    assert captured["url"].endswith("sendMessage")
    assert captured["payload"]["chat_id"] == 123
    assert captured["payload"]["text"] == "hello"
    assert captured["payload"]["reply_markup"] == rm
    assert captured["payload"]["parse_mode"] == "HTML"
    assert captured["payload"]["disable_web_page_preview"] is True
