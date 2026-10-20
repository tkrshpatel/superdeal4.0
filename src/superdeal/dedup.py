"""Deterministic duplicate matching for parsed deals.

Phase 4 intentionally avoids ML and external services. It produces an
explainable match decision from normalized merchant, product, and price.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .parser import Deal

_STOPWORDS = {
    "deal", "offer", "sale", "exclusive", "new", "launch", "live",
    "price", "only", "just", "available", "buy", "get",
}


def normalize_product_name(name: str) -> str:
    """Normalize marketing-heavy product names for comparison."""
    value = name.lower()
    value = re.sub(r"(?<=\d)\s+(?=gb|tb|mb|inch|in|mm|cm|kg|g\b)", "", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    tokens = [token for token in value.split() if token not in _STOPWORDS]
    return " ".join(tokens)


def product_tokens(name: str) -> set[str]:
    return set(normalize_product_name(name).split())


def product_similarity(left: str, right: str) -> float:
    """Return token Jaccard similarity between 0 and 1."""
    a, b = product_tokens(left), product_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass(frozen=True, slots=True)
class DuplicateDecision:
    is_duplicate: bool
    confidence: str
    reason: str


def match_deals(left: Deal, right: Deal) -> DuplicateDecision:
    """Classify whether two deals represent the same underlying deal.

    Exact merchant/product/price is a strong duplicate. Same merchant and
    highly similar product with a price change is also the same product deal,
    allowing price history to capture the change. Uncertain matches are kept
    separate rather than merged.
    """
    if left.merchant and right.merchant and left.merchant.lower() != right.merchant.lower():
        return DuplicateDecision(False, "low", "different merchants")

    similarity = product_similarity(left.product_name, right.product_name)
    same_product = similarity >= 0.75
    same_price = left.deal_price is not None and left.deal_price == right.deal_price

    if same_product and same_price:
        return DuplicateDecision(True, "high", "same merchant, product and price")

    if same_product and left.merchant and right.merchant:
        return DuplicateDecision(True, "medium", "same merchant and similar product; price differs")

    if similarity >= 0.90 and (left.merchant is None or right.merchant is None):
        return DuplicateDecision(True, "medium", "highly similar product; merchant unavailable")

    return DuplicateDecision(False, "low", "insufficient similarity")
