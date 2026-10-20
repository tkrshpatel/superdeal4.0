import sqlite3

from superdeal.database import connect, upsert_deal
from superdeal.intelligence import get_price_history, price_intelligence


def seed_deal(db: sqlite3.Connection) -> int:
    return upsert_deal(
        db,
        duplicate_hash="intel-1",
        product_name="Test Phone",
        deal_price=1000,
        merchant="Amazon",
        source_url="https://amazon.in/p",
        raw_text="Phone",
        observed_at="2026-09-30T00:00:00Z",
        source_channel="c",
        source_message_id="1",
    )


def test_price_intelligence_tracks_low_high_previous_and_change():
    db = connect(":memory:")
    deal_id = seed_deal(db)
    upsert_deal(
        db, duplicate_hash="intel-1", product_name="Test Phone", deal_price=900,
        merchant="Amazon", source_url="https://amazon.in/p", raw_text="Phone",
        observed_at="2026-09-30T01:00:00Z", source_channel="c", source_message_id="2",
    )
    upsert_deal(
        db, duplicate_hash="intel-1", product_name="Test Phone", deal_price=950,
        merchant="Amazon", source_url="https://amazon.in/p", raw_text="Phone",
        observed_at="2026-09-30T02:00:00Z", source_channel="c", source_message_id="3",
    )

    assert get_price_history(db, deal_id) == [
        {"price": 1000, "observed_at": "2026-09-30T00:00:00Z"},
        {"price": 900, "observed_at": "2026-09-30T01:00:00Z"},
        {"price": 950, "observed_at": "2026-09-30T02:00:00Z"},
    ]
    info = price_intelligence(db, deal_id)
    assert info["lowest_price"] == 900
    assert info["highest_price"] == 1000
    assert info["previous_price"] == 900
    assert info["change_pct"] == 5.56
    assert info["is_historical_low"] is False
    assert info["observations"] == 3


def test_price_intelligence_unknown_deal():
    db = connect(":memory:")
    assert price_intelligence(db, 999) is None
