import importlib.util
import re
import sys
import types
from pathlib import Path

if 'backend' not in sys.modules:
    backend = types.ModuleType('backend')
    backend.urls = lambda text: re.findall(r'https://[^\s]+', text)
    sys.modules['backend'] = backend
spec = importlib.util.spec_from_file_location('universal_image_enrichment', Path(__file__).with_name('image_enrichment.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_flipkart_image_template():
    u = 'https://rukminim2.flixcart.com/image/{@width}/{@height}/abc.jpeg'
    assert m.normalize_image_url(u) == 'https://rukminim2.flixcart.com/image/800/800/abc.jpeg'


def test_generic_retailer_source():
    assert m.source_urls('https://shop.example.com/p/123', []) == ['https://shop.example.com/p/123']


def test_multi_product_does_not_guess():
    text = 'https://shop.example.com/a https://shop.example.com/b'
    assert m.source_urls(text, []) == []
    assert m.source_urls(text, ['https://shop.example.com/b']) == ['https://shop.example.com/b']


def test_no_private_or_http():
    for url in ['http://shop.example.com/a', 'https://127.0.0.1/a', 'https://localhost/a',
                'https://server.internal/a', 'https://user:pass@shop.example.com/a']:
        assert not m.safe_url(url)


def test_found_and_fallback():
    product = [{'affiliate_urls': [], 'ecommerce_platform': 'independent shop'}]
    url = 'https://images.example.com/item.jpg'
    found = m.enrich_products('https://shop.example.com/p', product, scraper=lambda links, detailed: {'image_url': url, 'reason': None})
    assert found[0]['status'] == 'FOUND' and found[0]['image_url'] == url
    missed = m.enrich_products('https://shop.example.com/p', product, scraper=lambda links, detailed: {'reason': 'NO_CANDIDATE'})
    assert missed[0]['status'] == 'PLACEHOLDER'
    assert missed[0]['diagnostics']['reason'] == 'NO_CANDIDATE'


def test_legacy_scraper_compatibility():
    product = [{'affiliate_urls': []}]
    result = m.enrich_products('https://shop.example.com/p', product, scraper=lambda links: 'https://img.example.com/1.jpg')
    assert result[0]['status'] == 'FOUND'
