from superdeal.enrichment import enrich_deal, url_domain
from superdeal.parser import Deal


def test_enrichment_extracts_discount_coupon_card_and_return():
    deal = Deal(
        "Nike Running Shoes",
        2999,
        "https://fkrt.to/example",
        "Flipkart",
        "🔥 70% Off Nike Running Shoes\n7 days return\nExtra 10% off with ICICI Credit Card\nUse coupon",
    )
    result = enrich_deal(deal)
    assert result.discount_pct == 70
    assert result.return_days == 7
    assert result.has_coupon is True
    assert result.has_card_offer is True
    assert result.category_hint == "Fashion"


def test_enrichment_detects_home_category_and_cod():
    deal = Deal(
        "Wonderchef Galaxy Cooktop",
        3499,
        raw_text="Cash on delivery available",
    )
    result = enrich_deal(deal)
    assert result.category_hint == "Home & Kitchen"
    assert result.has_cod is True


def test_enrichment_is_conservative_when_signals_are_missing():
    result = enrich_deal(Deal("Unknown Product", 999, raw_text="Simple deal"))
    assert result.discount_pct is None
    assert result.return_days is None
    assert result.has_coupon is False
    assert result.has_card_offer is False
    assert result.has_cod is False
    assert result.category_hint is None


def test_url_domain_normalizes_hostname():
    assert url_domain("https://www.amazon.in/dp/example") == "amazon.in"
    assert url_domain(None) is None
