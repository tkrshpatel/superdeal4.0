from image_enrichment import enrich_products, PLACEHOLDER_IMAGE


def product():
    return {'affiliate_urls': ['https://earnkaro.com/deal'], 'ecommerce_platform': 'Amazon'}


def test_image_found_before_publication():
    calls = []
    def scrape(links):
        calls.extend(links)
        return 'https://m.media-amazon.com/images/I/product.jpg'
    results = enrich_products('Buy https://www.amazon.in/dp/B123', [product()], scraper=scrape)
    assert results[0]['status'] == 'FOUND'
    assert calls == ['https://www.amazon.in/dp/B123']


def test_missing_image_uses_placeholder():
    result = enrich_products('Buy https://www.amazon.in/dp/B123', [product()], scraper=lambda links: None)
    assert result[0]['status'] == 'PLACEHOLDER'
    assert result[0]['image_url'] == PLACEHOLDER_IMAGE


def test_scraper_failure_uses_placeholder():
    def fail(links): raise TimeoutError('blocked')
    result = enrich_products('Buy https://www.amazon.in/dp/B123', [product()], scraper=fail)
    assert result[0]['status'] == 'PLACEHOLDER'


def test_no_original_link_does_not_browse_affiliate():
    def fail(links): raise AssertionError('should not browse')
    result = enrich_products('No merchant link', [product()], scraper=fail)
    assert result[0]['status'] == 'PLACEHOLDER'
