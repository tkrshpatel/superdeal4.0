import pytest

from superdeal.telegram import TelegramAPIError, TelegramBotSource


def make_client(responses):
    calls = []

    def request(method, params):
        calls.append((method, params))
        return responses[len(calls) - 1]

    return TelegramBotSource("123:token", timeout=5, request=request), calls


def test_get_me_uses_bot_api():
    client, calls = make_client([{"ok": True, "result": {"id": 123, "username": "dealbot"}}])
    assert client.get_me()["username"] == "dealbot"
    assert calls == [("getMe", {})]


def test_channel_posts_are_converted_to_messages_and_offset_advances():
    client, calls = make_client([
        {
            "ok": True,
            "result": [
                {
                    "update_id": 10,
                    "channel_post": {
                        "message_id": 77,
                        "date": 1790000000,
                        "chat": {"id": -100123, "username": "deal_channel", "title": "Deals"},
                        "text": "OnePlus Pad 2 @ 29699",
                    },
                }
            ],
        },
        {"ok": True, "result": []},
    ])

    messages = client.fetch_messages("@deal_channel")
    assert len(messages) == 1
    assert messages[0].message_id == "77"
    assert messages[0].text == "OnePlus Pad 2 @ 29699"
    assert messages[0].observed_at.endswith("+00:00")

    client.fetch_updates()
    assert calls[1][1]["offset"] == 11


def test_private_channel_without_username_matches_numeric_chat_id():
    client, _ = make_client([
        {
            "ok": True,
            "result": [
                {
                    "update_id": 20,
                    "channel_post": {
                        "message_id": 88,
                        "date": 1790000000,
                        "chat": {"id": -1004397807961, "title": "Super Deals 3.0"},
                        "text": "Samsung 1TB SSD @ 5999",
                    },
                }
            ],
        }
    ])

    messages = client.fetch_messages("-1004397807961")
    assert len(messages) == 1
    assert messages[0].message_id == "88"


def test_numeric_chat_id_with_at_prefix_is_supported():
    client, _ = make_client([
        {
            "ok": True,
            "result": [
                {
                    "update_id": 21,
                    "channel_post": {
                        "message_id": 89,
                        "date": 1790000000,
                        "chat": {"id": -1004397807961, "title": "Super Deals 3.0"},
                        "text": "SSD @ 5999",
                    },
                }
            ],
        }
    ])

    assert len(client.fetch_messages("@-1004397807961")) == 1


def test_invite_token_does_not_match_a_channel_username():
    client, _ = make_client([
        {
            "ok": True,
            "result": [
                {
                    "update_id": 22,
                    "channel_post": {
                        "message_id": 90,
                        "date": 1790000000,
                        "chat": {"id": -1004397807961, "title": "Super Deals 3.0"},
                        "text": "Should not match",
                    },
                }
            ],
        }
    ])

    assert client.fetch_messages("@+a6CzJXbwHeMyYWZl") == []


def test_caption_is_supported():
    client, _ = make_client([
        {
            "ok": True,
            "result": [
                {
                    "update_id": 1,
                    "channel_post": {
                        "message_id": 2,
                        "date": 1790000000,
                        "chat": {"id": -1001, "username": "deals"},
                        "caption": "Wonderchef @ 3499",
                    },
                }
            ],
        }
    ])
    assert client.fetch_messages("deals")[0].text == "Wonderchef @ 3499"


def test_telegram_error_is_raised():
    client, _ = make_client([{"ok": False, "description": "Unauthorized"}])
    with pytest.raises(TelegramAPIError, match="Unauthorized"):
        client.get_me()


def test_token_and_limits_are_validated():
    with pytest.raises(ValueError):
        TelegramBotSource("")

    client, _ = make_client([])
    with pytest.raises(ValueError):
        client.fetch_updates(limit=101)


def test_channel_name_matching_is_case_and_whitespace_insensitive():
    client, _ = make_client([
        {
            "ok": True,
            "result": [
                {
                    "update_id": 30,
                    "channel_post": {
                        "message_id": 31,
                        "date": 1790000000,
                        "chat": {"id": -1004397807961, "title": "  Super   Deals 3.0  "},
                        "text": "Name matching @ 5999",
                    },
                }
            ],
        }
    ])

    messages = client.fetch_messages(" super deals 3.0 ")
    assert len(messages) == 1
    assert messages[0].message_id == "31"


def test_public_username_matching_remains_case_insensitive():
    client, _ = make_client([
        {
            "ok": True,
            "result": [
                {
                    "update_id": 32,
                    "channel_post": {
                        "message_id": 33,
                        "date": 1790000000,
                        "chat": {"id": -100123, "username": "Deal_Channel", "title": "Deals"},
                        "text": "Username matching @ 5999",
                    },
                }
            ],
        }
    ])

    assert len(client.fetch_messages("@DEAL_CHANNEL")) == 1


def test_close_is_available_for_worker_lifecycle():
    client, _ = make_client([])
    assert client.close() is None
