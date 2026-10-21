"""Rolling one-hour duplicate matching is based on normalized product names."""
from superdeal_phase2_full.backend import product_name_key, select_new_products


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
