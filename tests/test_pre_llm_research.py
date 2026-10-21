"""Invariants for experimental pre-LLM product research."""
import json
import sys
from pathlib import Path

# Backend modules are intentionally stored in this standalone source directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'superdeal_phase2_full'))

import pytest

from backend import Backend
from pre_llm_research import fill_missing_mrp, llm_evidence, research_images, usable_product_title, clean_price_evidence, select_description, select_product_name, browser_failure, persist_research, load_research

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


def test_flipkart_meta_description_preserves_only_product_copy():
    raw = ("Flipkart.com: Buy {TITLE} for Rs. {PRICE} from Flipkart.com. "
           "Formulated with a blend of nourishing ingredients, this face wash "
           "is suitable for all skin types, offering a refreshing cleanse "
           "without causing irritation - Lowest Prices, Only Genuine Products, "
           "30 Day Replacement Guarantee, Free Shipping.")
    result = select_description({'description': None, 'meta_description': raw}, 'www.flipkart.com')
    assert result == ("Formulated with a blend of nourishing ingredients, this face wash "
                      "is suitable for all skin types, offering a refreshing cleanse "
                      "without causing irritation")
    assert '{TITLE}' not in result
    assert 'Free Shipping' not in result


def test_description_fallback_does_not_change_other_retailers():
    assert select_description({'description': 'Genuine product description.'}, 'amazon.in') == 'Genuine product description.'
    assert select_description({'description': '{TITLE} placeholder'}, 'www.flipkart.com') is None


def test_amazon_prefers_real_product_title_over_accessibility_heading():
    facts = {
        'heading': 'Product summary presents key product information Keyboard shortcut shift + alt + opt + D',
        'description': 'Samsung Galaxy A56 5G Mobile (Awesome Violet Glow, 8GB, 128GB) : Amazon.in: Electronics',
        'amazon_product_title': 'Samsung Galaxy A56 5G Mobile (Awesome Violet Glow, 8GB, 128GB)',
    }
    assert select_product_name(facts, 'www.amazon.in') == facts['amazon_product_title']
    facts['amazon_product_title'] = None
    assert select_product_name(facts, 'www.amazon.in') == 'Samsung Galaxy A56 5G Mobile (Awesome Violet Glow, 8GB, 128GB)'


def test_amazon_does_not_use_generic_h1_when_product_title_missing():
    facts = {'heading': 'Product summary presents key product information Keyboard shortcut', 'product_name': None}
    assert select_product_name(facts, 'www.amazon.in') is None
    assert select_product_name({'heading': 'Actual product heading'}, 'www.flipkart.com') == 'Actual product heading'


def test_browser_errors_have_diagnostic_categories():
    assert browser_failure(RuntimeError('net::ERR_CONNECTION_RESET while loading URL')) == 'NETWORK_ERR_CONNECTION_RESET'
    assert browser_failure(RuntimeError('navigation timeout')) == 'TIMEOUT'
    assert browser_failure(RuntimeError('other browser issue')) == 'BROWSER_RUNTIMEERROR'


def test_amazon_price_fallback_and_mrp_distinction():
    evidence = clean_price_evidence({
        'amazon_price': '₹26,999.00',
        'amazon_mrp': '₹32,999.00',
    })
    assert evidence['price'] == 26999.0
    assert evidence['price_source'] == 'amazon_price_to_pay'
    assert evidence['mrp'] == 32999.0
    assert evidence['mrp_source'] == 'amazon_basis_price'


def test_amazon_price_does_not_replace_structured_offer_or_accept_template():
    evidence = clean_price_evidence({
        'json_ld_price': '25999',
        'json_ld_price_currency': 'INR',
        'amazon_price': '₹26,999',
        'amazon_mrp': '{PRICE}',
    })
    assert evidence['price'] == 25999.0
    assert evidence['mrp'] is None


def test_amazon_mrp_below_sale_price_is_rejected():
    evidence = clean_price_evidence({'amazon_price': '₹999', 'amazon_mrp': '₹899'})
    assert evidence['price'] == 999.0
    assert evidence['mrp'] is None


class FakePlaywrightCollection:
    def __init__(self):
        self.docs = []

    def insert_many(self, docs, ordered=True):
        self.docs.extend(docs)

    def find(self, query):
        return [doc for doc in self.docs if doc['raw_id'] == query['raw_id']]


def test_playwright_raw_roundtrip_to_llm_uses_saved_exact_links():
    store = FakePlaywrightCollection()
    text = 'First ' + URL1 + ' second ' + URL2
    records = {
        URL1: {'status': 'FOUND', 'product_name': 'Samsung phone', 'price': 26999.0,
               'price_source': 'amazon_price_to_pay', 'image_url': 'https://cdn.example.com/a.jpg'},
        URL2: {'status': 'NETWORK_ERR_HTTP2_PROTOCOL_ERROR', 'product_name': None,
               'price': None, 'image_url': None},
    }
    persist_research(store, 'message-42', text, records)
    assert len(store.docs) == 2
    assert all(doc['source'] == 'playwright' for doc in store.docs)
    assert {doc['affiliate_url'] for doc in store.docs} == {URL1, URL2}
    # Ensure Mistral consumes the database copy, not a modified in-memory dict.
    records[URL1]['price'] = 1.0
    restored = load_research(store, 'message-42', text)
    assert restored[URL1]['price'] == 26999.0
    llm_text = llm_evidence(text, restored)
    assert '"price": 26999.0' in llm_text
    assert Backend.validate(response([product(URL1), product(URL2)]), text)


def test_playwright_raw_rejects_rewritten_or_missing_links():
    store = FakePlaywrightCollection()
    with pytest.raises(ValueError, match='exact EarnKaro'):
        persist_research(store, 'x', URL1, {'https://amazon.in/changed': {'price': 99}})
    assert not store.docs
    with pytest.raises(ValueError, match='exact EarnKaro'):
        persist_research(store, 'x', URL1 + ' ' + URL2, {URL1: {'price': 99}})


def test_playwright_raw_fails_closed_on_missing_or_duplicate_snapshot():
    store = FakePlaywrightCollection()
    persist_research(store, 'x', URL1, {URL1: {'status': 'FOUND'}})
    with pytest.raises(ValueError, match='Incomplete'):
        load_research(store, 'x', URL1 + ' ' + URL2)
    store.docs.append(dict(store.docs[0]))
    with pytest.raises(ValueError, match='Incomplete'):
        load_research(store, 'x', URL1)


def test_missing_mrp_uses_only_exact_affiliate_link():
    first = product(URL1)
    first['deal_price'] = 27999.0
    second = product(URL2)
    research = {
        URL1: {'mrp': 49999.0},
        URL2: {'mrp': None},
    }
    fill_missing_mrp([first, second], research)
    assert first['original_price'] == 49999.0
    assert second['original_price'] is None
    assert first['affiliate_urls'] == [URL1]


def test_mrp_fallback_never_overwrites_llm_or_uses_lower_value():
    first = product(URL1)
    first['original_price'] = 45000.0
    second = product(URL2)
    second['deal_price'] = 500.0
    fill_missing_mrp([first, second], {URL1: {'mrp': 49999.0}, URL2: {'mrp': 400.0}})
    assert first['original_price'] == 45000.0
    assert second['original_price'] is None


def test_multiple_conflicting_mrps_do_not_get_assigned():
    offer = product(URL1)
    offer['affiliate_urls'] = [URL1, URL2]
    fill_missing_mrp([offer], {URL1: {'mrp': 799.0}, URL2: {'mrp': 999.0}})
    assert offer['original_price'] is None
