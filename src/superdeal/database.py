"""SQLite persistence for SuperDeal 3.0."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    duplicate_hash TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    merchant TEXT,
    current_price INTEGER,
    source_url TEXT,
    affiliate_url TEXT,
    page_title TEXT,
    canonical_url TEXT,
    image_url TEXT,
    verified_price INTEGER,
    last_verified_at TEXT,
    description TEXT,
    brand TEXT,
    mrp INTEGER,
    enriched_merchant TEXT,
    page_discount_pct INTEGER,
    llm_brand_name TEXT,
    llm_original_price INTEGER,
    llm_current_price INTEGER,
    llm_platform TEXT,
    llm_product TEXT,
    llm_discount_pct INTEGER,
    llm_model TEXT,
    llm_status TEXT NOT NULL DEFAULT 'pending',
    llm_error TEXT,
    enrichment_status TEXT NOT NULL DEFAULT 'pending',
    enrichment_error TEXT,
    raw_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    source_channel TEXT,
    source_message_id TEXT,
    source_url TEXT,
    raw_text TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    UNIQUE(source_channel, source_message_id)
);

CREATE TABLE IF NOT EXISTS telegram_raw_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_channel TEXT NOT NULL,
    source_message_id TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    content_hash TEXT,
    is_duplicate INTEGER NOT NULL DEFAULT 0,
    duplicate_of_id INTEGER REFERENCES telegram_raw_messages(id),
    UNIQUE(source_channel, source_message_id)
);

CREATE TABLE IF NOT EXISTS price_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    price INTEGER NOT NULL,
    observed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_deals_status ON deals(status);
CREATE INDEX IF NOT EXISTS idx_observations_deal ON source_observations(deal_id);
CREATE INDEX IF NOT EXISTS idx_telegram_raw_messages_channel
    ON telegram_raw_messages(source_channel, source_message_id);
CREATE INDEX IF NOT EXISTS idx_telegram_raw_messages_content_hash
    ON telegram_raw_messages(content_hash);
CREATE TABLE IF NOT EXISTS earnkaro_conversions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_raw_message_id INTEGER NOT NULL UNIQUE
        REFERENCES telegram_raw_messages(id) ON DELETE CASCADE,
    source_channel TEXT NOT NULL,
    source_message_id TEXT NOT NULL,
    request_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    provider_reference TEXT,
    response_text TEXT,
    response_payload TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_earnkaro_conversions_status
    ON earnkaro_conversions(status);

CREATE INDEX IF NOT EXISTS idx_price_history_deal ON price_history(deal_id);

CREATE TABLE IF NOT EXISTS deal_clicks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id INTEGER NOT NULL REFERENCES deals(id) ON DELETE CASCADE,
    clicked_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_deal_clicks_deal_time ON deal_clicks(deal_id, clicked_at);
"""

def connect(database_url: str | Path = "data/superdeal.db", *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open SQLite and initialize/migrate the schema."""
    path = str(database_url)
    if path.startswith("sqlite:///"):
        path = path[len("sqlite:///"):]
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=check_same_thread)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)

    columns = {row["name"] for row in connection.execute("PRAGMA table_info(deals)").fetchall()}
    migrations = {
        "affiliate_url": "TEXT",
        "page_title": "TEXT",
        "canonical_url": "TEXT",
        "image_url": "TEXT",
        "verified_price": "INTEGER",
        "last_verified_at": "TEXT",
        "description": "TEXT",
        "brand": "TEXT",
        "mrp": "INTEGER",
        "enriched_merchant": "TEXT",
        "page_discount_pct": "INTEGER",
        "llm_brand_name": "TEXT",
        "llm_original_price": "INTEGER",
        "llm_current_price": "INTEGER",
        "llm_platform": "TEXT",
        "llm_product": "TEXT",
        "llm_discount_pct": "INTEGER",
        "llm_model": "TEXT",
        "llm_status": "TEXT NOT NULL DEFAULT 'pending'",
        "llm_error": "TEXT",
        "enrichment_status": "TEXT NOT NULL DEFAULT 'pending'",
        "enrichment_error": "TEXT",
    }
    for name, definition in migrations.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE deals ADD COLUMN {name} {definition}")

    raw_columns = {
        row["name"] for row in connection.execute(
            "PRAGMA table_info(telegram_raw_messages)"
        ).fetchall()
    }
    raw_migrations = {
        "content_hash": "TEXT",
        "is_duplicate": "INTEGER NOT NULL DEFAULT 0",
        "duplicate_of_id": "INTEGER",
    }
    for name, definition in raw_migrations.items():
        if name not in raw_columns:
            connection.execute(
                f"ALTER TABLE telegram_raw_messages ADD COLUMN {name} {definition}"
            )

    # Backfill duplicate metadata for raw messages that predate this schema.
    legacy_rows = connection.execute(
        "SELECT id, raw_text FROM telegram_raw_messages "
        "WHERE content_hash IS NULL ORDER BY id"
    ).fetchall()
    for row in legacy_rows:
        content_hash = hashlib.sha256(row["raw_text"].encode("utf-8")).hexdigest()
        canonical = connection.execute(
            """SELECT id FROM telegram_raw_messages
               WHERE content_hash = ? AND raw_text = ? AND id < ?
               ORDER BY id LIMIT 1""",
            (content_hash, row["raw_text"], row["id"]),
        ).fetchone()
        connection.execute(
            """UPDATE telegram_raw_messages
               SET content_hash = ?, is_duplicate = ?, duplicate_of_id = ?
               WHERE id = ?""",
            (
                content_hash,
                1 if canonical else 0,
                int(canonical["id"]) if canonical else None,
                row["id"],
            ),
        )
    connection.commit()
    return connection


def record_raw_telegram_message(
    connection: sqlite3.Connection,
    *,
    source_channel: str,
    source_message_id: str,
    raw_text: str,
    observed_at: str,
    ingested_at: str | None = None,
) -> bool:
    """Persist the exact Telegram payload and tag exact-text duplicates.

    Duplicate detection is deliberately based only on the original message
    text. The first stored occurrence is canonical; later occurrences are
    retained in the raw ledger but marked as duplicates.
    """
    if not source_channel or not source_message_id:
        raise ValueError("source_channel and source_message_id are required")
    if not isinstance(raw_text, str):
        raise TypeError("raw_text must be a string")

    timestamp = ingested_at or observed_at
    content_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

    existing_message = connection.execute(
        """SELECT id FROM telegram_raw_messages
           WHERE source_channel = ? AND source_message_id = ?""",
        (source_channel, source_message_id),
    ).fetchone()
    if existing_message:
        return False

    canonical = connection.execute(
        """SELECT id FROM telegram_raw_messages
           WHERE content_hash = ? AND raw_text = ?
           ORDER BY id LIMIT 1""",
        (content_hash, raw_text),
    ).fetchone()

    is_duplicate = 1 if canonical else 0
    duplicate_of_id = int(canonical["id"]) if canonical else None

    connection.execute(
        """INSERT INTO telegram_raw_messages
           (source_channel, source_message_id, raw_text, observed_at, ingested_at,
            content_hash, is_duplicate, duplicate_of_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            source_channel,
            source_message_id,
            raw_text,
            observed_at,
            timestamp,
            content_hash,
            is_duplicate,
            duplicate_of_id,
        ),
    )
    connection.commit()
    return True


def upsert_deal(
    connection: sqlite3.Connection,
    *,
    duplicate_hash: str,
    product_name: str,
    deal_price: int | None,
    merchant: str | None,
    source_url: str | None,
    raw_text: str,
    affiliate_url: str | None = None,
    page_title: str | None = None,
    canonical_url: str | None = None,
    image_url: str | None = None,
    verified_price: int | None = None,
    last_verified_at: str | None = None,
    observed_at: str,
    source_channel: str | None = None,
    source_message_id: str | None = None,
) -> int:
    """Insert a deal or update its latest observation."""
    row = connection.execute(
        "SELECT id FROM deals WHERE duplicate_hash = ?", (duplicate_hash,)
    ).fetchone()

    if row:
        deal_id = int(row["id"])
        connection.execute(
            """UPDATE deals
               SET product_name = ?, merchant = ?, current_price = ?,
                   source_url = ?, affiliate_url = ?, raw_text = ?, last_seen_at = ?,
                   page_title = COALESCE(?, page_title),
                   canonical_url = COALESCE(?, canonical_url),
                   image_url = COALESCE(?, image_url),
                   verified_price = COALESCE(?, verified_price),
                   last_verified_at = COALESCE(?, last_verified_at)
               WHERE id = ?""",
            (product_name, merchant, deal_price, source_url, affiliate_url, raw_text, observed_at,
             page_title, canonical_url, image_url, verified_price, last_verified_at, deal_id),
        )
    else:
        cursor = connection.execute(
            """INSERT INTO deals
               (duplicate_hash, product_name, merchant, current_price, source_url, affiliate_url,
                page_title, canonical_url, image_url, verified_price, last_verified_at,
                raw_text, first_seen_at, last_seen_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (duplicate_hash, product_name, merchant, deal_price, source_url, affiliate_url,
             page_title, canonical_url, image_url, verified_price, last_verified_at,
             raw_text, observed_at, observed_at),
        )
        deal_id = int(cursor.lastrowid)

    if source_channel is not None or source_message_id is not None:
        connection.execute(
            """INSERT OR IGNORE INTO source_observations
               (deal_id, source_channel, source_message_id, source_url, raw_text, observed_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (deal_id, source_channel, source_message_id, source_url, raw_text, observed_at),
        )

    if deal_price is not None:
        latest = connection.execute(
            """SELECT price FROM price_history
               WHERE deal_id = ? ORDER BY id DESC LIMIT 1""", (deal_id,)
        ).fetchone()
        if latest is None or int(latest["price"]) != deal_price:
            connection.execute(
                "INSERT INTO price_history (deal_id, price, observed_at) VALUES (?, ?, ?)",
                (deal_id, deal_price, observed_at),
            )

    connection.commit()
    return deal_id


def get_deal(connection: sqlite3.Connection, deal_id: int) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
    return dict(row) if row else None
