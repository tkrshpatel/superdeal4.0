"""Rolling one-hour duplicate matching is based on normalized product names."""
from superdeal_phase2_full.backend import product_name_key, marketplace_key, product_duplicate_key, select_new_products


def test_product_name_case_punctuation_spacing():
    assert product_name_key("Samsung Galaxy A56 5G!") == product_name_key("  SAMSUNG, Galaxy A56 5G  ")
    assert product_name_key("Samsung Galaxy A56 5G") != product_name_key("Samsung Galaxy A56 8GB")


def test_duplicate_against_prior_publication():
    prior = {product_name_key("Samsung Galaxy A56 5G")}
    products = [
        {"product_name": "SAMSUNG galaxy A56 5G"},
        {"product_name": "Sony WH-1000XM5"},
    ]
    assert select_new_products(products, prior) == ([1], [0])


def test_duplicate_within_same_message():
    products = [
        {"product_name": "Sony WH-1000XM5"},
        {"product_name": "SONY WH 1000XM5"},
        {"product_name": "Marshall Emberton III"},
    ]
    assert select_new_products(products, set()) == ([0, 2], [1])


def test_no_match_for_distinct_product_models():
    prior = {product_name_key("Samsung Galaxy A56 5G 8GB 128GB")}
    new = [{"product_name": "Samsung Galaxy A56 5G 8GB 256GB"}]
    assert select_new_products(new, prior) == ([0], [])


def _deal(name, market):
    return {'product_name': name, 'ecommerce_platform': market}


def test_mens_and_bras_spelling_variants():
    assert product_name_key("Men's Bra") == product_name_key("Mens Bras")
    assert product_name_key("Men Bra") == product_name_key("Men's Bra's")


def test_same_marketplace_aliases_are_duplicates():
    prior = {product_duplicate_key(_deal("Men's Bra", "Amazon"))}
    candidate = [_deal("Mens Bras", "amazon.in"),
                 _deal("Men Bra", "Flipkart")]
    assert select_new_products(candidate, prior) == ([1], [0])
    assert marketplace_key("https://www.amazon.in/deal") == marketplace_key("Amazon India")


def test_same_name_from_two_marketplaces_is_not_duplicate():
    candidates = [_deal("Sony Headphones 128GB", "amazon.in"),
                  _deal("Sony Headphones 128GB", "Flipkart")]
    assert select_new_products(candidates, set()) == ([0, 1], [])


def test_variants_and_distinct_items_stay_separate_in_one_marketplace():
    prior = {product_duplicate_key(_deal("Samsung A56 8GB 128GB", "Amazon"))}
    candidates = [_deal("Samsung A56 8GB 256GB", "amazon.in"),
                  _deal("Samsung A55 8GB 128GB", "amazon.in"),
                  _deal("Samsung A56 8GB 128GB", "amazon.in")]
    assert select_new_products(candidates, prior) == ([0, 1], [2])
