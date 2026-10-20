from datetime import datetime, timezone

from superdeal.database import connect, upsert_deal
from superdeal.freshness import deal_freshness, expire_stale_deals, freshness_status, mark_stale_deals


NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def seed(db, observed_at="2026-09-30T10:00:00Z"):
    return upsert_deal(
        db, duplicate_hash="x", product_name="Phone", deal_price=999,
        merchant="Amazon", source_url="https://amazon.in/p", raw_text="Phone",
        observed_at=observed_at,
    )


def test_freshness_status():
    assert freshness_status("2026-09-30T10:00:00Z", now=NOW) == "fresh"
    assert freshness_status("2026-09-29T12:00:00Z", now=NOW) == "fresh"
    assert freshness_status("2026-09-29T11:59:59Z", now=NOW) == "stale"
    assert freshness_status("2026-10-01T00:00:00Z", now=NOW) == "future"


def test_mark_stale_deals():
    db = connect(":memory:")
    seed(db, "2026-09-28T10:00:00Z")
    assert mark_stale_deals(db, now=NOW) == 1
    assert db.execute("SELECT status FROM deals").fetchone()[0] == "stale"


def test_expire_stale_deals():
    db = connect(":memory:")
    seed(db, "2026-09-20T10:00:00Z")
    assert expire_stale_deals(db, now=NOW) == 1
    assert db.execute("SELECT status FROM deals").fetchone()[0] == "expired"


def test_deal_freshness_details():
    db = connect(":memory:")
    deal_id = seed(db)
    result = deal_freshness(db, deal_id, now=NOW)
    assert result["status"] == "fresh"
    assert result["age_hours"] == 2.0
    assert result["stale_after_hours"] == 24.0
    assert result["expire_after_hours"] == 168.0
    assert deal_freshness(db, 999, now=NOW) is None
