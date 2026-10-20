import pytest

from superdeal.database import connect
from superdeal.telegram import MockTelegramSource, TelegramMessage
from superdeal.worker import WorkerConfig, _ingest_stream_message, run_once


def test_config_from_environment(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "token")
    monkeypatch.setenv("TELEGRAM_CHANNELS", "@one, @two")
    config = WorkerConfig.from_env()
    assert config.token == "token"
    assert config.channels == ("@one", "@two")
    assert config.reader_mode == "bot"


def test_user_config_from_environment(monkeypatch):
    monkeypatch.setenv("TELEGRAM_READER_MODE", "user")
    monkeypatch.setenv("TELEGRAM_CHANNELS", "https://t.me/deals")
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "hash")
    config = WorkerConfig.from_env()
    assert config.reader_mode == "user"
    assert config.api_id == "12345"
    assert config.api_hash == "hash"


def test_config_validation():
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        WorkerConfig("", ("@one",)).validate()
    with pytest.raises(ValueError, match="TELEGRAM_CHANNELS"):
        WorkerConfig("token", ()).validate()


def test_user_config_validation():
    with pytest.raises(ValueError, match="TELEGRAM_API_ID"):
        WorkerConfig("", ("@one",), reader_mode="user", api_hash="hash").validate()


def test_run_once_ingests_all_configured_channels():
    source = MockTelegramSource([
        TelegramMessage("@one", "1", "OnePlus Pad 2 @ 29699 https://amazon.in/p/1", "2026-09-29T20:00:00+00:00"),
        TelegramMessage("@two", "2", "Wonderchef Cooktop @ 3499 https://example.com/p/2", "2026-09-29T20:01:00+00:00"),
    ])
    config = WorkerConfig("token", ("@one", "@two"), database_url=":memory:")
    assert run_once(config, source=source) == 2


def test_worker_persists_raw_without_creating_deal_before_earnkaro(tmp_path):
    db = tmp_path / "superdeal.db"
    source = MockTelegramSource([
        TelegramMessage("@one", "1", "OnePlus Pad 2 @ 29699 https://amazon.in/p/1", "2026-09-29T20:00:00+00:00"),
    ])
    config = WorkerConfig("token", ("@one",), database_url=str(db))
    assert run_once(config, source=source) == 1
    connection = connect(str(db))
    try:
        assert connection.execute("SELECT COUNT(*) FROM telegram_raw_messages").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM deals").fetchone()[0] == 0
    finally:
        connection.close()


def test_hybrid_config_validation():
    with pytest.raises(ValueError, match="TELEGRAM_API_ID"):
        WorkerConfig("token", ("@one",), reader_mode="hybrid").validate()


def test_hybrid_run_once_merges_bot_and_user_messages():
    class Source:
        def __init__(self, messages): self.messages = messages
        def fetch_messages_for_channels(self, channels, *, limit=100):
            return {channel: [m for m in self.messages if m.channel == channel] for channel in channels}
        def close(self): pass

    bot = Source([TelegramMessage("@one", "1", "Bot deal @ 100 https://example.com/b", "2026-09-29T20:00:00+00:00")])
    user = Source([
        TelegramMessage("@one", "1", "Duplicate bot deal @ 100 https://example.com/b", "2026-09-29T20:00:00+00:00"),
        TelegramMessage("@two", "2", "External deal @ 200 https://example.com/e", "2026-09-29T20:01:00+00:00"),
    ])
    config = WorkerConfig("token", ("@one", "@two"), database_url=":memory:", reader_mode="hybrid", api_id="1", api_hash="hash")
    assert run_once(config, source=(bot, user)) == 2

def test_exact_duplicate_telegram_messages_are_stored_but_only_one_is_queued():
    source = MockTelegramSource([
        TelegramMessage("@one", "1", "Same deal @ 100 https://example.com/p", "2026-10-03T07:00:00+00:00"),
        TelegramMessage("@two", "2", "Same deal @ 100 https://example.com/p", "2026-10-03T07:01:00+00:00"),
    ])
    config = WorkerConfig("token", ("@one", "@two"), database_url=":memory:")
    assert run_once(config, source=source) == 2


def test_stream_burst_persists_every_message_before_conversion(tmp_path):
    db = tmp_path / "burst.db"
    connection = connect(str(db), check_same_thread=False)
    try:
        messages = [
            TelegramMessage("@one", "101", "Deal one https://example.com/1", "2026-10-06T07:00:00+00:00"),
            TelegramMessage("@one", "102", "Deal two https://example.com/2", "2026-10-06T07:00:00+00:00"),
            TelegramMessage("@one", "103", "Deal three https://example.com/3", "2026-10-06T07:00:00+00:00"),
        ]
        for message in messages:
            _ingest_stream_message(connection, message)

        rows = connection.execute(
            "SELECT source_message_id, raw_text FROM telegram_raw_messages ORDER BY id"
        ).fetchall()
        assert [(row["source_message_id"], row["raw_text"]) for row in rows] == [
            ("101", "Deal one https://example.com/1"),
            ("102", "Deal two https://example.com/2"),
            ("103", "Deal three https://example.com/3"),
        ]
        assert connection.execute(
            "SELECT COUNT(*) FROM earnkaro_conversions"
        ).fetchone()[0] == 0
    finally:
        connection.close()
