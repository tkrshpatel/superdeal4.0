from datetime import datetime, timezone

from superdeal.database import connect, upsert_deal
from superdeal.llm_enrichment import LLMDealMetadata, enrich_pending_deals_with_llm


def test_llm_enrichment_writes_only_llm_fields_and_preserves_existing_data():
    db = connect(":memory:")
    now = datetime.now(timezone.utc).isoformat()
    deal_id = upsert_deal(
        db,
        duplicate_hash="llm-deal",
        product_name="More :",
        deal_price=389,
        merchant="Amazon",
        source_url="https://internal.example/source",
        affiliate_url="https://earnkaro.example/abc",
        raw_text="CANONICAL EARNKARO RESPONSE",
        observed_at=now,
    )
    db.execute(
        """UPDATE deals SET page_title=?, description=?, brand=?, mrp=?,
                  verified_price=?, canonical_url=?, image_url=?,
                  enrichment_status='enriched'
           WHERE id=?""",
        (
            "Turtle Men Cotton White Slim Fit Solid Formal Shirts : Amazon.in",
            "Turtle Men Cotton White Slim Fit Solid Formal Shirts",
            None,
            1999,
            399,
            "https://www.amazon.in/Turtle-Cotton-White-Formal-Shirts/dp/B0CCJKZGR6",
            None,
            deal_id,
        ),
    )
    db.commit()

    before = dict(db.execute("SELECT * FROM deals WHERE id=?", (deal_id,)).fetchone())

    def fake_interpreter(row):
        assert row["product_name"] == "More :"
        assert row["current_price"] == 389
        assert row["mrp"] == 1999
        return LLMDealMetadata(
            brand_name="Turtle",
            original_price=1999,
            current_price=389,
            ecommerce_platform="Amazon",
            product="Turtle Men Cotton White Slim Fit Solid Formal Shirt",
            discount_pct=81,
        )

    assert enrich_pending_deals_with_llm(db, interpreter=fake_interpreter) == 1
    after = dict(db.execute("SELECT * FROM deals WHERE id=?", (deal_id,)).fetchone())

    assert after["llm_brand_name"] == "Turtle"
    assert after["llm_original_price"] == 1999
    assert after["llm_current_price"] == 389
    assert after["llm_platform"] == "Amazon"
    assert after["llm_product"] == "Turtle Men Cotton White Slim Fit Solid Formal Shirt"
    assert after["llm_discount_pct"] == 81
    assert after["llm_status"] == "enriched"

    protected = (
        "product_name", "merchant", "current_price", "source_url", "affiliate_url",
        "page_title", "canonical_url", "image_url", "verified_price", "description",
        "brand", "mrp", "raw_text", "enrichment_status",
    )
    for field in protected:
        assert after[field] == before[field]


def test_llm_layer_waits_for_product_enrichment():
    db = connect(":memory:")
    now = datetime.now(timezone.utc).isoformat()
    upsert_deal(
        db,
        duplicate_hash="pending-deal",
        product_name="Pending",
        deal_price=100,
        merchant="Shop",
        source_url=None,
        affiliate_url="https://earnkaro.example/pending",
        raw_text="CANONICAL",
        observed_at=now,
    )
    assert enrich_pending_deals_with_llm(db, interpreter=lambda row: None) == 0
