import json

from superdeal.database import connect, record_raw_telegram_message
from superdeal.earnkaro import convert_message_via_api, process_pending_earnkaro, queue_unique_telegram_messages


def test_earnkaro_sends_entire_message_unchanged(monkeypatch):
    captured = {}

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"data": "Converted whole message"}

    def fake_post(url, *, headers, json, timeout):
        captured.update({"url": url, "headers": headers, "json": json, "timeout": timeout})
        return Response()

    monkeypatch.setattr("superdeal.earnkaro.requests.post", fake_post)

    message = "🔥 DEAL\nBuy now: https://example.com/a\nAlso: https://example.com/b"
    result = convert_message_via_api(message, "secret")

    assert result["response_text"] == "Converted whole message"
    assert captured["json"] == {"deal": message, "convert_option": "convert_only"}
    assert captured["headers"]["Authorization"] == "Bearer secret"


def test_only_canonical_telegram_messages_are_queued_for_earnkaro():
    connection = connect(":memory:")
    try:
        record_raw_telegram_message(
            connection,
            source_channel="@one",
            source_message_id="1",
            raw_text="Same exact message https://example.com/a",
            observed_at="2026-10-03T07:00:00+00:00",
        )
        record_raw_telegram_message(
            connection,
            source_channel="@two",
            source_message_id="2",
            raw_text="Same exact message https://example.com/a",
            observed_at="2026-10-03T07:01:00+00:00",
        )

        assert queue_unique_telegram_messages(connection) == 1
        row = connection.execute("SELECT * FROM earnkaro_conversions").fetchone()
        assert row["request_text"] == "Same exact message https://example.com/a"
        assert row["source_channel"] == "@one"
        assert row["source_message_id"] == "1"
    finally:
        connection.close()


def test_earnkaro_response_is_persisted(monkeypatch):
    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"data": "Converted message", "request_id": "ek-123"}

    monkeypatch.setattr(
        "superdeal.earnkaro.requests.post",
        lambda *args, **kwargs: Response(),
    )

    connection = connect(":memory:")
    try:
        original = "Product text https://example.com/product"
        record_raw_telegram_message(
            connection,
            source_channel="@one",
            source_message_id="10",
            raw_text=original,
            observed_at="2026-10-03T07:00:00+00:00",
        )
        assert queue_unique_telegram_messages(connection) == 1
        assert process_pending_earnkaro(connection, api_key="secret") == 1

        row = connection.execute("SELECT * FROM earnkaro_conversions").fetchone()
        assert row["status"] == "converted"
        assert row["request_text"] == original
        assert row["response_text"] == "Converted message"
        assert json.loads(row["response_payload"])["request_id"] == "ek-123"
        assert row["provider_reference"] == "ek-123"
        assert row["attempts"] == 1
    finally:
        connection.close()


def test_successful_earnkaro_response_is_the_only_deal_source(monkeypatch):
    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {
                "data": "EARNKARO PRODUCT Deal @ 499 https://amzn.to/converted",
                "request_id": "ek-canonical",
            }

    monkeypatch.setattr(
        "superdeal.earnkaro.requests.post",
        lambda *args, **kwargs: Response(),
    )

    connection = connect(":memory:")
    try:
        original = "TELEGRAM ORIGINAL Deal @ 9999 https://example.com/original"
        record_raw_telegram_message(
            connection,
            source_channel="@one",
            source_message_id="99",
            raw_text=original,
            observed_at="2026-10-03T07:00:00+00:00",
        )
        assert queue_unique_telegram_messages(connection) == 1
        assert connection.execute("SELECT COUNT(*) FROM deals").fetchone()[0] == 0

        assert process_pending_earnkaro(connection, api_key="secret") == 1

        deal = connection.execute("SELECT * FROM deals").fetchone()
        assert deal["raw_text"] == "EARNKARO PRODUCT Deal @ 499 https://amzn.to/converted"
        assert deal["product_name"] == "EARNKARO PRODUCT"
        assert deal["current_price"] == 499
        assert deal["affiliate_url"] == "https://amzn.to/converted"
        assert original not in deal["raw_text"]

        raw = connection.execute("SELECT raw_text FROM telegram_raw_messages").fetchone()
        assert raw["raw_text"] == original
    finally:
        connection.close()
