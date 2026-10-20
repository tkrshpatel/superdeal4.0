"""Guard against the mapping regression seen after the previous image patch."""
import copy
from image_enrichment import enrich_products, normalize_image_url, source_urls, safe_url


def deal(name, url):
    return {'product_name': name, 'affiliate_urls': [url], 'ecommerce_platform': 'other'}


def test_single_flipkart_shortlink_even_when_affiliate_matches_raw():
    url = 'https://fkrt.cc/zlF71rW'
    product = deal('Face wash', url)
    assert source_urls('Buy ' + url, [url], 'fkrt.cc', all_products=[product]) == [url]
    got = enrich_products('Buy ' + url, [product], scraper=lambda links: 'https://rukminim2.flixcart.com/image/800/800/a.jpeg')
    assert got[0]['status'] == 'FOUND'


def test_multi_product_never_cross_assigns_or_mutates_products():
    ps = [deal('Face wash', 'https://fkrt.cc/one'), deal('Hair oil', 'https://fkrt.cc/two')]
    original = copy.deepcopy(ps)
    calls = []
    def scraper(links):
        calls.append(links)
        return 'https://img.example.com/a.jpg'
    got = enrich_products('https://fkrt.cc/one https://fkrt.cc/two', ps, scraper=scraper)
    assert ps == original
    assert calls == [['https://fkrt.cc/one'], ['https://fkrt.cc/two']]
    assert [x['status'] for x in got] == ['FOUND', 'FOUND']


def test_multi_product_different_earnkaro_links_never_guess_source():
    ps = [deal('Face wash', 'https://ek.example.com/one'), deal('Hair oil', 'https://ek.example.com/two')]
    original = copy.deepcopy(ps)
    def scraper(links):
        raise AssertionError('ambiguous mapping must not scrape')
    got = enrich_products('https://fkrt.cc/one https://fkrt.cc/two', ps, scraper=scraper)
    assert ps == original
    assert [x['status'] for x in got] == ['PLACEHOLDER', 'PLACEHOLDER']
    assert all(x['diagnostics']['reason'] == 'AMBIGUOUS_OR_MISSING_SOURCE_LINK' for x in got)


def test_no_guess_when_single_raw_link_describes_multiple_products():
    ps = [deal('A', 'https://ek.example.com/one'), deal('B', 'https://ek.example.com/two')]
    assert source_urls('https://shop.example.com/shared', ps[0]['affiliate_urls'], all_products=ps) == []


def test_normalize_only_flipkart_image_not_affiliate_url():
    img = 'https://rukminim2.flixcart.com/image/{@width}/{@height}/a.jpeg'
    assert normalize_image_url(img).endswith('/800/800/a.jpeg')
    assert normalize_image_url('https://fkrt.cc/one') == 'https://fkrt.cc/one'


def test_reject_private_navigation():
    for url in ('https://127.0.0.1/admin', 'https://localhost/admin', 'http://example.com/a', 'https://user:pass@example.com/a'):
        assert not safe_url(url)
