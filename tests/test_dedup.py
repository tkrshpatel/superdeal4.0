from superdeal.dedup import match_deals, normalize_product_name, product_similarity
from superdeal.parser import Deal


def test_normalization_removes_marketing_words():
    assert normalize_product_name("🔥 BOLTT EVO Deal - Sale") == "boltt evo"


def test_same_product_different_channels_is_duplicate():
    left = Deal("BOLTT EVO Deal", 8999, merchant="Flipkart")
    right = Deal("BOLTT EVO SALE", 8999, merchant="Flipkart")
    decision = match_deals(left, right)
    assert decision.is_duplicate is True
    assert decision.confidence == "high"


def test_same_product_price_change_is_duplicate_for_price_history():
    left = Deal("OnePlus Pad 2 12GB RAM", 29699, merchant="Amazon")
    right = Deal("OnePlus Pad 2 12 GB RAM", 27999, merchant="Amazon")
    decision = match_deals(left, right)
    assert decision.is_duplicate is True
    assert decision.confidence == "medium"


def test_different_merchant_is_not_duplicate():
    left = Deal("Nike Running Shoes", 2999, merchant="Amazon")
    right = Deal("Nike Running Shoes", 2999, merchant="Flipkart")
    assert match_deals(left, right).is_duplicate is False


def test_unrelated_products_are_not_duplicate():
    left = Deal("Wonderchef Cooktop", 3499, merchant="Amazon")
    right = Deal("OnePlus Pad 2", 3499, merchant="Amazon")
    decision = match_deals(left, right)
    assert decision.is_duplicate is False
    assert product_similarity(left.product_name, right.product_name) < 0.75
