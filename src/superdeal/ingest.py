"""Telegram ingestion: persist original messages as an audit/input ledger only."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Iterable

from .database import record_raw_telegram_message
from .telegram import TelegramMessage


def ingest_messages(connection: sqlite3.Connection, messages: Iterable[TelegramMessage]) -> int:
    """Persist Telegram messages without creating downstream deal records.

    Raw Telegram text is retained only as the immutable input/audit ledger and
    as the request source for EarnKaro conversion. All deal parsing happens
    later from a successful EarnKaro response.
    """
    count = 0
    for message in messages:
        inserted = record_raw_telegram_message(
            connection,
            source_channel=message.channel,
            source_message_id=message.message_id,
            raw_text=message.text,
            observed_at=message.observed_at,
            ingested_at=datetime.now(timezone.utc).isoformat(),
        )
        if inserted:
            count += 1
    return count
