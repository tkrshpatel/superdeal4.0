"""Regression tests for preserving explicitly advertised current selling prices."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'superdeal_phase2_full'))

from price_reconciliation import apply_verified_prices, extract_explicit_prices

A = 'https://amzn.to/4yCH1Pp'
B = 'https://custom-affiliate.example/x?campaign=abc'


def offer(url, price=None):
    return {'product_name': 'Deal item', 'affiliate_urls': [url],
            'deal_price': price, 'original_price': 39999.0}


def test_redmi_price_survives_coupon_bank_promotion():
    msg = ('Redmi Note 15 at 25999\n\n' + A
           + '\n\nApply 1500 off Coupon + Pay with AXIS/ICICI Credit Card')
    products = [offer(A, None)]
    assert extract_explicit_prices(msg) == {A: 25999.0}
    assert apply_verified_prices(products, msg) == 1
    assert products[0]['deal_price'] == 25999.0
    assert products[0]['original_price'] == 39999.0


def test_earnkaro_message_overrides_wrong_model_selling_price():
    products = [offer(A, 1500)]
    assert apply_verified_prices(products, 'Redmi Note 15 at 25999\n' + A) == 1
    assert products[0]['deal_price'] == 25999.0


def test_single_product_telegram_fallback_when_converted_text_drops_price():
    products = [offer(A)]
    raw = 'Redmi Note 15 at 25999\n' + B + '\nApply 1500 off Coupon'
    assert apply_verified_prices(products, 'Redmi Note 15\n' + A, raw_text=raw) == 1
    assert products[0]['deal_price'] == 25999.0


def test_coupon_only_cannot_become_selling_price():
    msg = 'Redmi Note 15\n' + A + '\nApply 1500 off Coupon'
    products = [offer(A)]
    assert extract_explicit_prices(msg) == {}
    assert apply_verified_prices(products, msg) == 0
    assert products[0]['deal_price'] is None


def test_two_products_get_their_own_prices():
    msg = 'Redmi Note 15 at 25999\n' + A + '\nWatch at 1999\n' + B
    products = [offer(A), offer(B)]
    assert apply_verified_prices(products, msg) == 2
    assert [p['deal_price'] for p in products] == [25999.0, 1999.0]


def test_no_cross_assignment_from_raw_when_many_links():
    msg = 'Redmi Note 15\n' + A + '\nWatch\n' + B
    raw = 'Redmi Note 15 at 25999\n' + A + '\nWatch at 1999\n' + B
    products = [offer(A), offer(B)]
    assert apply_verified_prices(products, msg, raw_text=raw) == 0
    assert all(p['deal_price'] is None for p in products)


def test_merchant_fallback_only_for_same_exact_link():
    products = [offer(A)]
    assert apply_verified_prices(products, 'Redmi\n' + A,
                                 research={A: {'price': 24999.0}, B: {'price': 999.0}}) == 1
    assert products[0]['deal_price'] == 24999.0


def test_no_mrp_or_card_amount_as_selling_price():
    msg = 'Phone MRP ₹49999\n' + A + '\n₹1500 cashback on ICICI Card'
    assert extract_explicit_prices(msg) == {}
