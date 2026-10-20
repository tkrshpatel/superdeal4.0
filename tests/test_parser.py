from superdeal.parser import duplicate_hash, parse_deal
import pytest


def test_amazon_deal():
    d = parse_deal("""🔥 Lowest : atomberg Efficio Exhaust Fan 200mm (8 Inches) | BLDC Motor

Deal @ 1499 Only

https://amzn.to/4dfDtuG""")
    assert d.product_name == "Lowest : atomberg Efficio Exhaust Fan 200mm (8 Inches) | BLDC Motor"
    assert d.deal_price == 1499
    assert d.merchant == "Amazon"
    assert d.source_url == "https://amzn.to/4dfDtuG"


def test_flipkart_product():
    d = parse_deal("""📱 New Launch : OPPO K14 Plus 5G
Deal @ 26000
✔️ Rs.4000 off with multiple cards
https://fkrt.to/514Sx0kH""")
    assert "OPPO K14 Plus 5G" in d.product_name
    assert d.deal_price == 26000
    assert d.merchant == "Flipkart"


def test_percentage_only_message_is_allowed_without_price():
    d = parse_deal("🔥 85 to 90% Off https://fkrt.to/McPcWX13")
    assert d.deal_price is None
    assert d.merchant == "Flipkart"


def test_gift_card_uses_explicit_at_price():
    d = parse_deal("Rs.10,000 Flipkart Gift Card @ ₹9,250 only https://app.cred.club/x")
    assert d.deal_price == 9250


def test_multiple_urls_keep_first_as_source():
    d = parse_deal("""Pepe Jeans Clothing
Men's : https://amzn.to/4zmFJsL
Women's : https://amzn.to/3To199t""")
    assert d.source_url == "https://amzn.to/4zmFJsL"


def test_duplicate_ignores_url_and_message_wording():
    a = parse_deal("BOLTT EVO ₹8,999 https://fkrt.to/one")
    b = parse_deal("BOLTT EVO SALE IS LIVE ₹8,999 https://fkrt.to/two")
    assert duplicate_hash(a) == duplicate_hash(b)


def test_invalid_input():
    with pytest.raises(ValueError):
        parse_deal("")


def test_competitor_price_does_not_become_deal_price():
    d = parse_deal("""Presto Ultra Strong Disinfectant Toilet Cleaner 5L
Deal @ 341 or 359
Harpic price is Rs.900 -1000 for 5L
https://amzn.to/3T5vz08""")
    assert d.deal_price == 341
