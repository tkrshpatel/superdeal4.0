"""Credential-free deal enrichment utilities.

Phase 5 extracts useful metadata from the parsed deal text and URL without
calling external services. Real page fetching can be added later.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

from .parser import Deal

_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*(?:off|discount)", re.I)
_RETURN_RE = re.compile(r"(\d+)\s*[- ]?days?\s*return", re.I)
_COUPON_RE = re.compile(r"coupon|promo code|voucher", re.I)
_CARD_RE = re.compile(r"(?:sbi|hdfc|icici|axis|amex|credit card|debit card)", re.I)
_COD_RE = re.compile(r"cash on delivery|\bcod\b", re.I)


@dataclass(frozen=True, slots=True)
class DealEnrichment:
    discount_pct: float | None
    return_days: int | None
    has_coupon: bool
    has_card_offer: bool
    has_cod: bool
    category_hint: str | None


def _category_hint(product_name: str) -> str | None:
    value = product_name.lower()
    rules = (
        (("phone", "mobile", "smartphone", "iphone", "oneplus", "oppo"), "Electronics"),
        (("pad", "tablet", "laptop", "headphone", "earbud", "watch", "tv"), "Electronics"),
        (("cooktop", "cookware", "mixer", "fan", "cleaner", "vacuum"), "Home & Kitchen"),
        (("shirt", "jeans", "saree", "shoe", "sneaker", "dress"), "Fashion"),
        (("cream", "shampoo", "beauty", "makeup", "perfume"), "Beauty & Personal Care"),
        (("toy", "kids", "baby"), "Kids"),
        (("cricket", "fitness", "gym", "treadmill"), "Sports & Fitness"),
        (("car", "bike", "helmet", "tyre"), "Automotive"),
        (("book", "novel"), "Books"),
    )
    for keywords, category in rules:
        if any(keyword in value for keyword in keywords):
            return category
    return None


def enrich_deal(deal: Deal) -> DealEnrichment:
    """Extract conservative metadata from product name and raw message."""
    text = deal.raw_text or ""
    discount_match = _PERCENT_RE.search(text)
    return_match = _RETURN_RE.search(text)
    return DealEnrichment(
        discount_pct=float(discount_match.group(1)) if discount_match else None,
        return_days=int(return_match.group(1)) if return_match else None,
        has_coupon=bool(_COUPON_RE.search(text)),
        has_card_offer=bool(_CARD_RE.search(text)),
        has_cod=bool(_COD_RE.search(text)),
        category_hint=_category_hint(deal.product_name),
    )


def url_domain(url: str | None) -> str | None:
    """Return normalized hostname for downstream enrichment."""
    if not url:
        return None
    return urlparse(url).netloc.lower().removeprefix("www.") or None
