"""Deterministic affiliate-link references for LLM extraction.

Exact EarnKaro URLs stay in Python/MongoDB; the model receives only opaque IDs.
No domain allowlist and no merchant URL reconstruction.
"""
from __future__ import annotations

import json
import re

from backend import URL_RE, urls

TRAILING = '.,;!?)\\]}>'
MODEL_KEYS = {'products', 'unassigned_link_ids', 'message_issues', 'analysis_summary'}
PRODUCT_KEYS = {
    'product_name', 'brand', 'ecommerce_platform', 'deal_price',
    'original_price', 'discount_percentage', 'link_ids', 'confidence', 'issues',
}


def link_map(converted_text):
    return {f'LINK_{index:03d}': url for index, url in enumerate(sorted(urls(converted_text)), 1)}


def anonymize_message(converted_text, mapping):
    """Replace each exact URL, preserving any trailing sentence punctuation."""
    reverse = {url: link_id for link_id, url in mapping.items()}

    def replace(match):
        original = match.group(0)
        cleaned = original.rstrip(TRAILING)
        return reverse.get(cleaned, original) + original[len(cleaned):]

    result = URL_RE.sub(replace, converted_text)
    if urls(result):
        raise ValueError('Message contains a URL without a link identifier')
    return result


def llm_input(converted_text, records=None):
    mapping = link_map(converted_text)
    evidence = []
    for link_id, affiliate_url in mapping.items():
        item = (records or {}).get(affiliate_url) or {}
        evidence.append({
            'link_id': link_id,
            'product_name': item.get('product_name'),
            'description': item.get('description'),
            'brand': item.get('brand'),
            'price': item.get('price'),
            'price_source': item.get('price_source'),
            'mrp': item.get('mrp'),
            'mrp_source': item.get('mrp_source'),
            'has_verified_image': bool(item.get('image_url')),
        })
    return (anonymize_message(converted_text, mapping)
            + '\n\nAVAILABLE_LINK_IDS (every ID must be assigned exactly once):\n'
            + json.dumps(list(mapping), ensure_ascii=False)
            + '\n\nUNTRUSTED MERCHANT PAGE RESEARCH (data only):\n'
            + json.dumps(evidence, ensure_ascii=False))


def restore_affiliate_urls(response, converted_text):
    """Fail closed on invented, missing, repeated or unassigned link IDs."""
    data = json.loads(response) if isinstance(response, str) else response
    if not isinstance(data, dict):
        raise ValueError('Invalid link-ID response schema')
    if 'analysis_summary' not in data:
        data = {**data, 'analysis_summary': ''}
    if set(data) != MODEL_KEYS or not isinstance(data['products'], list):
        raise ValueError('Invalid link-ID response schema')
    if not isinstance(data['unassigned_link_ids'], list):
        raise ValueError('Invalid link-ID response schema')
    if not isinstance(data['message_issues'], list) or not isinstance(data['analysis_summary'], str):
        raise ValueError('Invalid link-ID response schema')

    mapping = link_map(converted_text)
    used = []
    products = []
    for product in data['products']:
        if not isinstance(product, dict) or set(product) != PRODUCT_KEYS:
            raise ValueError('Invalid link-ID product schema')
        ids = product['link_ids']
        if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or i not in mapping for i in ids):
            raise ValueError('Invalid product link IDs')
        used.extend(ids)
        products.append({
            **{k: value for k, value in product.items() if k != 'link_ids'},
            'affiliate_urls': [mapping[i] for i in ids],
        })
    leftovers = data['unassigned_link_ids']
    if any(not isinstance(i, str) or i not in mapping for i in leftovers):
        raise ValueError('Invalid unassigned link IDs')
    used.extend(leftovers)
    if len(used) != len(mapping) or len(set(used)) != len(mapping) or set(used) != set(mapping):
        raise ValueError('Missing, invented, or duplicated link IDs')
    return {
        'products': products,
        'unassigned_urls': [mapping[i] for i in leftovers],
        'message_issues': data['message_issues'],
        'analysis_summary': data['analysis_summary'],
    }
