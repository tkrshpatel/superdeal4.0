from datetime import datetime, timezone
from types import SimpleNamespace
from superdeal.telegram_user import TelegramUserSource

NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)

def test_direct_telethon_message():
    raw = SimpleNamespace(id=5, message='exact original', raw_text='exact original', text='exact original', date=NOW)
    result = TelegramUserSource.message_from_event(raw, 'telegram:4372803033')
    assert result.text == 'exact original'
    assert result.message_id == '5'
    assert result.channel == 'telegram:4372803033'

def test_telethon_event_wrapper():
    raw = SimpleNamespace(id=4, message='original', raw_text='original', date=NOW)
    event = SimpleNamespace(message=raw, chat=SimpleNamespace(username='dhonideals'))
    result = TelegramUserSource.message_from_event(event, 'telegram:4372803033')
    assert result.text == 'original'
    assert result.channel == '@dhonideals'

def test_media_only_skipped():
    raw = SimpleNamespace(id=3, message='', raw_text='', date=NOW)
    assert TelegramUserSource.message_from_event(raw, 'telegram:4372803033') is None

def test_naive_utc_date():
    raw = SimpleNamespace(id=2, message='text', raw_text='text', date=NOW.replace(tzinfo=None))
    result = TelegramUserSource.message_from_event(raw, 'telegram:4372803033')
    assert result.observed_at.endswith('+00:00')
