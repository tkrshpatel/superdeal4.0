"""Credential-free product-page metadata enrichment for canonical affiliate URLs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class WebMetadata:
    title: str | None = None
    description: str | None = None
    brand: str | None = None
    canonical_url: str | None = None
    image_url: str | None = None
    price: int | None = None
    mrp: int | None = None
    merchant: str | None = None
    discount_pct: int | None = None


class _MetadataParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.metadata: dict[str, str] = {}
        self._title_parts: list[str] = []
        self._in_title = False
        self._in_json_ld = False
        self._json_ld_parts: list[str] = []
        self.json_ld: list[object] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value for key, value in attrs}
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        if tag == "script" and (values.get("type") or "").lower() == "application/ld+json":
            self._in_json_ld = True
            self._json_ld_parts = []
        if tag == "meta":
            key = (values.get("property") or values.get("name") or values.get("itemprop") or "").lower()
            content = values.get("content")
            if key and content:
                self.metadata[key] = content.strip()
        if tag == "link" and "canonical" in (values.get("rel") or "").lower() and values.get("href"):
            self.metadata["canonical"] = urljoin(self.base_url, values["href"])

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag == "script" and self._in_json_ld:
            self._in_json_ld = False
            raw = "".join(self._json_ld_parts).strip()
            if raw:
                try:
                    self.json_ld.append(json.loads(raw))
                except (json.JSONDecodeError, TypeError):
                    pass

    def handle_data(self, data: str) -> None:
        if self._in_title and data.strip():
            self._title_parts.append(data.strip())
        if self._in_json_ld:
            self._json_ld_parts.append(data)


def _price(value: object) -> int | None:
    if value is None:
        return None
    text = str(value)
    match = re.search(r"(?:₹|INR|Rs\.?)?[\s]*([\d,]+(?:\.\d+)?)", text, re.I)
    if not match:
        return None
    try:
        return int(round(float(match.group(1).replace(",", ""))))
    except ValueError:
        return None


def _walk_json(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _product_json_ld(documents: list[object]) -> dict:
    for document in documents:
        for node in _walk_json(document):
            kind = node.get("@type")
            kinds = kind if isinstance(kind, list) else [kind]
            if any(str(item).lower() == "product" for item in kinds if item):
                return node
    return {}


def _image(value: object, base_url: str) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl")
    return urljoin(base_url, str(value)) if value else None


def parse_html_metadata(html: str, *, source_url: str) -> WebMetadata:
    parser = _MetadataParser(source_url)
    parser.feed(html)
    product = _product_json_ld(parser.json_ld)
    offers = product.get("offers") if isinstance(product.get("offers"), dict) else {}
    brand_value = product.get("brand")
    if isinstance(brand_value, dict):
        brand_value = brand_value.get("name")

    title = product.get("name") or " ".join(parser._title_parts).strip() or parser.metadata.get("og:title")
    description = (
        product.get("description")
        or parser.metadata.get("og:description")
        or parser.metadata.get("description")
    )
    image = (
        _image(product.get("image"), source_url)
        or _image(parser.metadata.get("og:image"), source_url)
        or _image(parser.metadata.get("og:image:url"), source_url)
        or _image(parser.metadata.get("twitter:image"), source_url)
        or _image(parser.metadata.get("twitter:image:src"), source_url)
        or _image(parser.metadata.get("image"), source_url)
    )
    price = _price(
        offers.get("price")
        or offers.get("lowPrice")
        or parser.metadata.get("product:price:amount")
        or parser.metadata.get("og:price:amount")
    )
    mrp = _price(
        offers.get("highPrice")
        or parser.metadata.get("product:original_price:amount")
        or parser.metadata.get("product:price:standard_amount")
    )
    return WebMetadata(
        title=str(title)[:500] if title else None,
        description=str(description)[:2000] if description else None,
        brand=str(brand_value)[:200] if brand_value else None,
        canonical_url=parser.metadata.get("canonical") or parser.metadata.get("og:url"),
        image_url=image,
        price=price,
        mrp=mrp,
    )


def fetch_web_metadata(url: str, *, timeout: float = 8.0) -> WebMetadata:
    """Follow the affiliate redirect internally and read public product metadata."""
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9",
            "Cache-Control": "no-cache",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type.lower():
            return WebMetadata()
        final_url = response.geturl()
        html = response.read(1_500_000).decode("utf-8", errors="replace")
    metadata = parse_html_metadata(html, source_url=final_url)
    if metadata.canonical_url:
        return metadata
    return WebMetadata(
        title=metadata.title,
        description=metadata.description,
        brand=metadata.brand,
        canonical_url=final_url,
        image_url=metadata.image_url,
        price=metadata.price,
        mrp=metadata.mrp,
    )
