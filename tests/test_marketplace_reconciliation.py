"""Marketplace fallback must be verified, per-link, and non-destructive."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'superdeal_phase2_full'))

from marketplace_reconciliation import marketplace_from_page_url, fill_missing_marketplace
from affiliate_link_ids import llm_input

A = 'https://any-shortener.invalid/p/1'
B = 'https://other-shortener.invalid/p/2'


def test_verified_redirect_destination_identifies_marketplace():
    assert marketplace_from_page_url('https://www.amazon.in/gp/product/ABCD') == 'Amazon'
    assert marketplace_from_page_url('https://www.flipkart.com/item/p/itm123') == 'Flipkart'
    assert marketplace_from_page_url('https://www.myntra.com/item/123') == 'Myntra'


def test_no_guess_from_shortener_or_similar_lookalike_domain():
    assert marketplace_from_page_url(A) is None
    assert marketplace_from_page_url('https://amazon.in.fraud.example/deal') is None
    assert marketplace_from_page_url('https://shop.example.org/item') is None


def test_missing_marketplace_filled_only_from_exact_link():
    products = [{'ecommerce_platform': None, 'affiliate_urls': [A]},
                {'ecommerce_platform': None, 'affiliate_urls': [B]}]
    count = fill_missing_marketplace(products, {A: {'marketplace': 'Amazon'}})
    assert count == 1
    assert products[0]['ecommerce_platform'] == 'Amazon'
    assert products[1]['ecommerce_platform'] is None


def test_explicit_marketplace_not_overwritten():
    products = [{'ecommerce_platform': 'Flipkart', 'affiliate_urls': [A]}]
    assert fill_missing_marketplace(products, {A: {'marketplace': 'Amazon'}}) == 0
    assert products[0]['ecommerce_platform'] == 'Flipkart'


def test_conflicting_multi_link_research_does_not_guess():
    products = [{'ecommerce_platform': None, 'affiliate_urls': [A, B]}]
    count = fill_missing_marketplace(products, {A: {'marketplace': 'Amazon'}, B: {'marketplace': 'Flipkart'}})
    assert count == 0
    assert products[0]['ecommerce_platform'] is None


def test_mistral_evidence_contains_marketplace_without_affiliate_url():
    result = llm_input('Phone ' + A, {A: {'marketplace': 'Amazon'}})
    assert '"marketplace": "Amazon"' in result
    assert A not in result
    assert 'LINK_001' in result
