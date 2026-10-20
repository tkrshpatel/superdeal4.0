from superdeal.database import connect
from superdeal.ingest import ingest_messages
from superdeal.telegram import MockTelegramSource, TelegramMessage


def test_mock_source_filters_channel_and_limit():
    source = MockTelegramSource([
        TelegramMessage("deals_a", "1", "BOLTT EVO Deal @ 8999 https://fkrt.to/a", "2026-09-30T00:00:00Z"),
        TelegramMessage("deals_b", "2", "Other Deal @ 499 https://amzn.to/b", "2026-09-30T00:01:00Z"),
        TelegramMessage("deals_a", "3", "Another Deal @ 999 https://amzn.to/c", "2026-09-30T00:02:00Z"),
    ])
    assert [m.message_id for m in source.fetch_messages("deals_a", limit=1)] == ["1"]


def test_ingest_persists_raw_message_without_creating_deal():
    db = connect(":memory:")
    message = TelegramMessage(
        "deals_a", "42",
        "ORIGINAL TELEGRAM Deal @ 8999 https://fkrt.to/a",
        "2026-09-30T00:00:00Z",
    )
    assert ingest_messages(db, [message]) == 1

    raw = db.execute("SELECT * FROM telegram_raw_messages").fetchone()
    assert raw["raw_text"] == message.text
    assert raw["source_channel"] == "deals_a"
    assert raw["source_message_id"] == "42"
    assert db.execute("SELECT COUNT(*) FROM deals").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM source_observations").fetchone()[0] == 0


def test_duplicate_raw_messages_are_retained_but_not_parsed_into_deals():
    db = connect(":memory:")
    messages = [
        TelegramMessage("deals_a", "1", "Same Telegram payload", "2026-09-30T00:00:00Z"),
        TelegramMessage("deals_b", "9", "Same Telegram payload", "2026-09-30T00:01:00Z"),
    ]
    assert ingest_messages(db, messages) == 2
    assert db.execute("SELECT COUNT(*) FROM telegram_raw_messages").fetchone()[0] == 2
    assert db.execute("SELECT COUNT(*) FROM deals").fetchone()[0] == 0
    duplicate = db.execute(
        "SELECT is_duplicate FROM telegram_raw_messages WHERE source_channel = 'deals_b'"
    ).fetchone()
    assert duplicate["is_duplicate"] == 1
