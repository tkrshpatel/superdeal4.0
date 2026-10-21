"""Conservative merchant identification from actual product-page hostnames.

Never assume an affiliate shortener indicates the final marketplace.
"""
from urllib.parse import urlsplit


def marketplace_from_page_url(page_url):
    try:
        parts = urlsplit(page_url or '')
        host = (parts.hostname or '').lower().rstrip('.')
        if parts.scheme not in ('https', 'http') or not host:
            return None
    except (TypeError, ValueError):
        return None
    retailers = {
        'amazon.in': 'Amazon',
        'amazon.com': 'Amazon',
        'flipkart.com': 'Flipkart',
        'myntra.com': 'Myntra',
        'ajio.com': 'AJIO',
        'tatacliq.com': 'Tata CLiQ',
        'nykaa.com': 'Nykaa',
        'jiomart.com': 'JioMart',
        'meesho.com': 'Meesho',
        'snapdeal.com': 'Snapdeal',
        'croma.com': 'Croma',
        'reliancedigital.in': 'Reliance Digital',
    }
    for domain, name in retailers.items():
        if host == domain or host.endswith('.' + domain):
            return name
    return None


def fill_missing_marketplace(products, research):
    """Only fill unknown marketplace using matching affiliate-link evidence."""
    count = 0
    for product in products:
        if str(product.get('ecommerce_platform') or '').strip():
            continue
        matched = {
            record['marketplace']
            for url in product.get('affiliate_urls') or []
            for record in [research.get(url) or {}]
            if isinstance(record.get('marketplace'), str) and record['marketplace'].strip()
        }
        # If multiple affiliate links disagree, never pick one arbitrarily.
        if len(matched) == 1:
            product['ecommerce_platform'] = next(iter(matched))
            count += 1
    return count
