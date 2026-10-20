"""Simple Telegram deal parser.

Phase 1 intentionally extracts only the reliable core:
product name, deal price, source URL and raw message.
Everything else can be enriched later by scraping the linked page.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
DEAL_PRICE_RE = re.compile(r"(?:deal|offer|price|now)\s*@\s*(?:₹|Rs\.?|INR)?\s*([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)
AT_PRICE_RE = re.compile(r"@\s*(?:₹|Rs\.?|INR)?\s*([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)
PRICE_RE = re.compile(r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d{1,2})?)", re.IGNORECASE)

MERCHANTS = {
    "amazon.in": "Amazon", "amazon.com": "Amazon", "amzn.to": "Amazon",
    "flipkart.com": "Flipkart", "fkrt.to": "Flipkart", "myntra.com": "Myntra",
    "ajio.com": "AJIO", "meesho.com": "Meesho", "croma.com": "Croma",
    "tatacliq.com": "Tata CLiQ", "nykaa.com": "Nykaa",
}

@dataclass(slots=True)
class Deal:
    product_name: str
    deal_price: int | None = None
    source_url: str | None = None
    merchant: str | None = None
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

def _clean_url(url: str) -> str:
    return url.rstrip(".,;!?)\]}>\"'")

def _merchant(url: str | None) -> str | None:
    if not url:
        return None
    host = urlparse(url).netloc.lower().removeprefix("www.")
    for domain, name in MERCHANTS.items():
        if host == domain or host.endswith("." + domain):
            return name
    return None

def _product_name(text: str) -> str:
    for line in text.splitlines():
        line = re.sub(r"https?://\S+", "", line).strip()
        line = re.sub(r"^[\W_]+", "", line).strip()
        if not line:
            continue
        inline = re.split(r"(?:deal|offer|price|now)\s*@", line, maxsplit=1, flags=re.I)
        if len(inline) == 2:
            candidate = inline[0].strip()
            if candidate:
                return re.sub(r"\s*[-:|]+\s*$", "", candidate).strip()[:300]
        if re.search(r"(?:₹|Rs\.?|INR)\s*[\d,]+", line, re.I):
            continue
        if re.search(r"\d+\s*%\s*(?:off|discount)", line, re.I):
            continue
        if re.fullmatch(r"(?:buy|shop|get)\s+now\W*", line, re.I):
            continue
        return line[:300]
    return "Unknown product"

def _deal_price(text: str) -> int | None:
    match = DEAL_PRICE_RE.search(text) or AT_PRICE_RE.search(text)
    if match:
        return int(float(match.group(1).replace(",", "")))
    prices = PRICE_RE.findall(text)
    if len(prices) == 1:
        return int(float(prices[0].replace(",", "")))
    return None

def parse_deal(text: str, *, source_channel: str | None = None, source_message_id: str | None = None) -> Deal:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Deal message must be a non-empty string.")
    urls = [_clean_url(u) for u in URL_RE.findall(text)]
    source_url = urls[0] if urls else None
    return Deal(product_name=_product_name(text), deal_price=_deal_price(text), source_url=source_url, merchant=_merchant(source_url), raw_text=text)

def duplicate_hash(deal: Deal) -> str:
    """Basic duplicate identity; URL is deliberately ignored."""
    product = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", deal.product_name.lower())).strip()
    key = "|".join([deal.merchant or "", product, str(deal.deal_price or "")])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
