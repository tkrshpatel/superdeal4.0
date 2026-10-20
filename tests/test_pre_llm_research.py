"""Invariants for experimental pre-LLM product research."""
import json
import sys
from pathlib import Path

# Backend modules are intentionally stored in this standalone source directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'superdeal_phase2_full'))

import pytest

from backend import Backend
from pre_llm_research import llm_evidence, research_images, usable_product_title, clean_price_evidence

URL1 = "https://fkrt.cc/alpha"
URL2 = "https://earnkaro.com/beta"


def product(url, name="Example product"):
    return {
        'product_name': name, 'brand': None, 'ecommerce_platform': None,
        'deal_price': None, 'original_price': None, 'discount_percentage': None,
        'affiliate_urls': [url], 'confidence': 90, 'issues': []
    }


def response(products):
    return json.dumps({
        'products': products, 'unassigned_urls': [],
        'message_issues': [], 'analysis_summary': 'verified'
    })


def test_research_does_not_change_earnkaro_url():
    text = "First " + URL1 + " second " + URL2
    records = {URL1: {'product_name': 'Phone', 'description': 'merchant facts',
                      'brand': 'Brand', 'image_url': 'https://cdn.example.com/phone.jpg'}}
    enriched = llm_evidence(text, records)
    assert enriched.startswith(text)
    assert URL1 in enriched and URL2 in enriched
    # Validation against original EarnKaro response remains the authority.
    assert Backend.validate(response([product(URL1), product(URL2)]), text)['products'][0]['affiliate_urls'] == [URL1]


def test_rejects_modified_affiliate_even_if_in_research():
    text = "Deal " + URL1
    with pytest.raises(ValueError, match="Missing, invented"):
        Backend.validate(response([product('https://www.flipkart.com/redirected')]), text)


def test_images_only_attach_to_their_exact_link():
    products = [product(URL1), product(URL2)]
    records = {URL1: {'image_url': 'https://cdn.example.com/phone.jpg'},
               URL2: {'image_url': None}}
    original = json.dumps(products, sort_keys=True)
    images = research_images(products, records)
    assert images[0]['status'] == 'FOUND'
    assert images[1]['status'] == 'PLACEHOLDER'
    assert json.dumps(products, sort_keys=True) == original


def test_promotional_logo_not_used_as_image():
    products = [product(URL1)]
    records = {URL1: {'image_url': None, 'product_name': 'Phone'}}
    assert research_images(products, records)[0]['image_url'] == '/superdeal-placeholder.svg'


def test_unresolved_flipkart_title_is_rejected():
    title = "{TITLE} - Price in India, Buy {TITLE} Online In India, Reviews, Ratings & Features | Flipkart.com"
    assert usable_product_title(title) is None
    assert usable_product_title("Nat Habit Acne Control Face Wash 100ml") == "Nat Habit Acne Control Face Wash 100ml"


def test_image_only_research_does_not_invent_product_name():
    records = {URL1: {'product_name': None, 'image_url': 'https://cdn.example.com/facewash.jpg'}}
    assert 'facewash.jpg' not in llm_evidence("Deal " + URL1, records)
    assert research_images([product(URL1)], records)[0]['status'] == 'FOUND'


def test_product_page_price_fallback_evidence():
    facts = {'json_ld_price': '₹349', 'json_ld_price_currency': 'INR',
             'meta_price': '399', 'meta_price_currency': 'INR'}
    result = clean_price_evidence(facts)
    assert result['price'] == 349.0
    assert result['price_source'] == 'json_ld_offer'
    converted = 'A deal without a price ' + URL1
    records = {URL1: {'product_name': 'Face wash', **result}}
    output = llm_evidence(converted, records)
    assert output.startswith(converted)
    assert '"price": 349.0' in output
    assert URL1 in output


def test_rejects_unresolved_price_and_wrong_currency():
    assert clean_price_evidence({'meta_price': '{PRICE}'})['price'] is None
    assert clean_price_evidence({'json_ld_price': '450', 'json_ld_price_currency': 'USD'})['price'] is None
    assert clean_price_evidence({'meta_price': '₹299 - ₹599'})['price'] is None


def test_mrp_not_confused_with_price():
    result = clean_price_evidence({'json_ld_price': '349', 'mrp': '599', 'mrp_source': 'list_price'})
    assert result['price'] == 349
    assert result['mrp'] == 599
    assert clean_price_evidence({'json_ld_price': '599', 'mrp': '349'})['mrp'] is None
