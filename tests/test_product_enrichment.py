from datetime import datetime, timezone

from superdeal.database import connect, upsert_deal
from superdeal.product_enrichment import enrich_pending_deals
from superdeal.web_enrichment import WebMetadata


def test_enrichment_is_additive_and_preserves_earnkaro_canonical_fields():
    db = connect(":memory:")
    now = datetime.now(timezone.utc).isoformat()
    upsert_deal(
        db, duplicate_hash="deal", product_name="Canonical EarnKaro title",
        deal_price=999, merchant="Amazon", source_url="https://internal.example/product",
        affiliate_url="https://earnkaro.example/abc",
        raw_text="CANONICAL EARNKARO RESPONSE", observed_at=now,
    )

    seen = []
    def fake_fetch(url):
        seen.append(url)
        return WebMetadata(
            title="Merchant page title", description="Product description",
            brand="BrandCo", canonical_url="https://merchant.example/p/1",
            image_url="https://merchant.example/image.jpg", price=1099, mrp=1999,
            merchant="Amazon", discount_pct=45,
        )

    assert enrich_pending_deals(db, fetcher=fake_fetch) == 1
    row = db.execute("SELECT * FROM deals").fetchone()
    assert seen == ["https://earnkaro.example/abc"]
    assert row["raw_text"] == "CANONICAL EARNKARO RESPONSE"
    assert row["affiliate_url"] == "https://earnkaro.example/abc"
    assert row["product_name"] == "Canonical EarnKaro title"
    assert row["image_url"] == "https://merchant.example/image.jpg"
    assert row["description"] == "Product description"
    assert row["brand"] == "BrandCo"
    assert row["mrp"] == 1999
    assert row["verified_price"] == 1099
    assert row["enriched_merchant"] == "Amazon"
    assert row["page_discount_pct"] == 45
    assert row["merchant"] == "Amazon"
    assert row["current_price"] == 999
    assert row["enrichment_status"] == "enriched"
