"""Conservative, deterministic deal-price recovery from deal message text.

Never interpret coupon/card/cashback/MRP figures as current selling prices.
The converted EarnKaro message is authoritative when it contains a clear price.
"""
from __future__ import annotations

import re

from affiliate_link_ids import link_map, anonymize_message

AMOUNT = r'(?:₹\s*|(?:rs\.?|inr)\s*)?((?:\d{1,3}(?:,\d{3})+|\d{3,7})(?:\.\d{1,2})?)'
AT_PRICE = re.compile(r'\b(?:at|for|price\s*[:=]|deal\s*price\s*[:=]|selling\s*price\s*[:=])\s*' + AMOUNT + r'\b', re.I)
RUPEE_PRICE = re.compile(r'(?:₹\s*|\b(?:rs\.?|inr)\s*)' + AMOUNT + r'\b', re.I)
BAD_CONTEXT = re.compile(r'coupon|cashback|card|bank|axis|icici|hdfc|sbi|off\b|discount|save\b|mrp|original|list\s*price|emi|exchange', re.I)


def _line_price(line):
    """Accept one unambiguous base selling price on a non-promotional line."""
    if BAD_CONTEXT.search(line):
        return None
    values = []
    for pattern in (AT_PRICE, RUPEE_PRICE):
        for match in pattern.finditer(line):
            amount = float(match.group(1).replace(',', ''))
            if 1 <= amount <= 10000000:
                values.append(amount)
    unique = set(values)
    return unique.pop() if len(unique) == 1 else None


def extract_explicit_prices(converted_text):
    """Only assign prices to link IDs where nearby price is unambiguous.

    Segment messages at each LINK_ID and use the closest preceding nonempty
    product line(s), never unrelated later coupon/bank instructions.
    """
    mapping = link_map(converted_text)
    if not mapping:
        return {}
    masked = anonymize_message(converted_text, mapping)
    lines = [line.strip() for line in masked.splitlines() if line.strip()]
    if not lines:
        return {}
    result = {}
    # One-line entries like "Product at 25999 LINK_001" are supported.
    for i, line in enumerate(lines):
        identifiers = re.findall(r'\bLINK_\d{3,}\b', line)
        if len(identifiers) != 1 or identifiers[0] not in mapping:
            continue
        link_id = identifiers[0]
        candidates = []
        same_line = _line_price(line)
        if same_line is not None:
            candidates.append(same_line)
        # Only look immediately before the link: a single price/product line,
        # optionally preceded by a title. Never reach past a previous link.
        for previous in lines[max(0, i - 2):i]:
            if re.search(r'\bLINK_\d{3,}\b', previous):
                candidates = []
                break
            price = _line_price(previous)
            if price is not None:
                candidates.append(price)
        if candidates and len(set(candidates)) == 1:
            result[mapping[link_id]] = candidates[0]
    return result


def apply_verified_prices(products, converted_text, *, raw_text=None, research=None):
    """Overwrite model selling price only when source price is unambiguous.

    Original Telegram text is fallback only for a *single* link, because
    original links may differ from EarnKaro's converted affiliate URLs.
    """
    mapping = link_map(converted_text)
    extracted = extract_explicit_prices(converted_text)
    if raw_text and len(mapping) == 1 and not extracted:
        # Handle a source URL independent of the EarnKaro converted URL.
        from backend import URL_RE
        original_links = URL_RE.findall(raw_text)
        if len(original_links) == 1:
            source_with_converted_link = URL_RE.sub(next(iter(mapping.values())), raw_text)
            explicit = extract_explicit_prices(source_with_converted_link)
        elif not original_links:
            explicit = extract_explicit_prices(raw_text + '\n' + next(iter(mapping.values())))
        else:
            explicit = {}
        if explicit:
            extracted[next(iter(mapping.values()))] = next(iter(explicit.values()))
    count = 0
    for product in products:
        attached = product.get('affiliate_urls') or []
        if not attached:
            continue
        known = {extracted[u] for u in attached if u in extracted}
        if len(known) == 1 and all(u in extracted for u in attached):
            price = next(iter(known))
            if product.get('deal_price') != price:
                product['deal_price'] = price
                count += 1
        elif product.get('deal_price') is None and research:
            merchant = {research[u]['price'] for u in attached
                        if u in research and type(research[u].get('price')) in (int, float)}
            if len(merchant) == 1 and len(attached) == 1:
                product['deal_price'] = next(iter(merchant))
                count += 1
    return count
