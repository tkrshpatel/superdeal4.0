"""Regression tests: Telegram Web chat IDs without public usernames."""
from types import SimpleNamespace

import pytest

from superdeal.telegram_user import TelegramUserReaderError, TelegramUserSource


def make_source(dialogs):
    source = object.__new__(TelegramUserSource)
    source.client = SimpleNamespace(get_dialogs=lambda limit=None: dialogs)
    return source


def test_web_link_resolves_matching_dialog(monkeypatch):
    from telethon import utils
    entity = SimpleNamespace(id=4403122058)
    other = SimpleNamespace(id=12345)
    monkeypatch.setattr(utils, "get_peer_id", lambda obj: -100 * (10**10) - obj.id)
    source = make_source([SimpleNamespace(entity=other), SimpleNamespace(entity=entity)])
    assert source._resolve_entity("https://web.telegram.org/k/#-4403122058") is entity


def test_unavailable_web_link_fails_without_guessing():
    source = make_source([])
    with pytest.raises(TelegramUserReaderError, match="not found in this"):
        source._resolve_entity("https://web.telegram.org/k/#-4403122058")


def test_public_username_still_uses_existing_resolver():
    source = object.__new__(TelegramUserSource)
    entity = object()
    source.client = SimpleNamespace(get_entity=lambda name: entity if name == "dhonideals" else None)
    assert source._resolve_entity("@dhonideals") is entity
