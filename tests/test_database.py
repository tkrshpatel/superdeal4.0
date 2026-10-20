from superdeal.database import connect, get_deal, record_raw_telegram_message, upsert_deal


def test_schema_and_first_insert():
    db = connect(":memory:")
    deal_id = upsert_deal(
        db, duplicate_hash="abc", product_name="BOLTT EVO", deal_price=8999,
        merchant="Flipkart", source_url="https://fkrt.to/a", raw_text="BOLTT EVO ₹8,999",
        observed_at="2026-09-30T00:00:00Z", source_channel="channel_a", source_message_id="1",
    )
    deal = get_deal(db, deal_id)
    assert deal["product_name"] == "BOLTT EVO"
    assert deal["current_price"] == 8999


def test_duplicate_observations_share_one_canonical_deal():
    db = connect(":memory:")
    kwargs = dict(
        duplicate_hash="same", product_name="BOLTT EVO", deal_price=8999,
        merchant="Flipkart", raw_text="BOLTT EVO ₹8,999",
        observed_at="2026-09-30T00:00:00Z",
    )
    first = upsert_deal(db, source_url="https://fkrt.to/a",
                        source_channel="channel_a", source_message_id="1", **kwargs)
    second = upsert_deal(
        db, source_url="https://fkrt.to/b", source_channel="channel_b", source_message_id="2",
        **{**kwargs, "observed_at": "2026-09-30T00:01:00Z", "raw_text": "SALE BOLTT EVO ₹8,999"},
    )
    assert first == second
    assert db.execute("SELECT COUNT(*) FROM deals").fetchone()[0] == 1
    assert db.execute("SELECT COUNT(*) FROM source_observations").fetchone()[0] == 2


def test_price_history_only_records_price_changes():
    db = connect(":memory:")
    kwargs = dict(
        duplicate_hash="p1", product_name="Phone", merchant="Amazon",
        source_url="https://amzn.to/a", raw_text="Phone", source_channel="c",
    )
    upsert_deal(db, deal_price=1000, observed_at="2026-09-30T00:00:00Z",
                source_message_id="1", **kwargs)
    upsert_deal(db, deal_price=1000, observed_at="2026-09-30T01:00:00Z",
                source_message_id="2", **kwargs)
    upsert_deal(db, deal_price=900, observed_at="2026-09-30T02:00:00Z",
                source_message_id="3", **kwargs)
    rows = db.execute("SELECT price FROM price_history ORDER BY id").fetchall()
    assert [r[0] for r in rows] == [1000, 900]


def test_database_url_style_is_supported(tmp_path):
    path = tmp_path / "db" / "superdeal.db"
    db = connect(f"sqlite:///{path}")
    assert db.execute("SELECT 1").fetchone()[0] == 1


def test_affiliate_url_is_persisted():
    db = connect(":memory:")
    deal_id = upsert_deal(
        db, duplicate_hash="aff", product_name="Phone", deal_price=1000,
        merchant="Amazon", source_url="https://amazon.in/p",
        affiliate_url="https://example.com/track?id=1", raw_text="Phone",
        observed_at="2026-09-30T00:00:00Z",
    )
    assert get_deal(db, deal_id)["affiliate_url"] == "https://example.com/track?id=1"


def test_web_metadata_is_persisted():
    db = connect(":memory:")
    deal_id = upsert_deal(
        db, duplicate_hash="web", product_name="Phone", deal_price=1000,
        merchant="Amazon", source_url="https://amazon.in/p", raw_text="Phone",
        page_title="Phone Pro", canonical_url="https://amazon.in/p/123",
        image_url="https://amazon.in/i.jpg", verified_price=999,
        last_verified_at="2026-09-30T01:00:00Z",
        observed_at="2026-09-30T00:00:00Z",
    )
    deal = get_deal(db, deal_id)
    assert deal["page_title"] == "Phone Pro"
    assert deal["canonical_url"] == "https://amazon.in/p/123"
    assert deal["image_url"] == "https://amazon.in/i.jpg"
    assert deal["verified_price"] == 999
    assert deal["last_verified_at"] == "2026-09-30T01:00:00Z"


def test_raw_telegram_message_is_preserved_exactly():
    db = connect(":memory:")
    raw = "Myntra Loot : Upto 89% Off On Roadster Clothing.\n\nMens \nJeans : https://myntr.it/qmu9Js5"
    inserted = record_raw_telegram_message(
        db,
        source_channel="@amazinglootsdealsoffers",
        source_message_id="12345",
        raw_text=raw,
        observed_at="2026-10-03T06:49:04+00:00",
        ingested_at="2026-10-03T06:49:05+00:00",
    )
    assert inserted is True
    row = db.execute(
        "SELECT source_channel, source_message_id, raw_text, observed_at, ingested_at "
        "FROM telegram_raw_messages"
    ).fetchone()
    assert tuple(row) == (
        "@amazinglootsdealsoffers",
        "12345",
        raw,
        "2026-10-03T06:49:04+00:00",
        "2026-10-03T06:49:05+00:00",
    )
    assert record_raw_telegram_message(
        db,
        source_channel="@amazinglootsdealsoffers",
        source_message_id="12345",
        raw_text="changed",
        observed_at="later",
    ) is False
    assert db.execute("SELECT COUNT(*) FROM telegram_raw_messages").fetchone()[0] == 1
    assert db.execute("SELECT raw_text FROM telegram_raw_messages").fetchone()[0] == raw


def test_exact_duplicate_message_is_retained_and_tagged():
    db = connect(":memory:")
    raw = "Same deal message exactly\nhttps://example.com/p"
    assert record_raw_telegram_message(
        db, source_channel="@one", source_message_id="1", raw_text=raw,
        observed_at="2026-10-03T07:00:00+00:00",
        ingested_at="2026-10-03T07:00:01+00:00",
    ) is True
    assert record_raw_telegram_message(
        db, source_channel="@two", source_message_id="2", raw_text=raw,
        observed_at="2026-10-03T07:01:00+00:00",
        ingested_at="2026-10-03T07:01:01+00:00",
    ) is True
    rows = db.execute(
        """SELECT id, source_channel, source_message_id, raw_text,
                  is_duplicate, duplicate_of_id
           FROM telegram_raw_messages ORDER BY id"""
    ).fetchall()
    assert rows[0]["is_duplicate"] == 0
    assert rows[1]["is_duplicate"] == 1
    assert rows[1]["duplicate_of_id"] == rows[0]["id"]
