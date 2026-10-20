"""Browser-backed product enrichment with the existing HTTP fetcher as fallback."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from .web_enrichment import WebMetadata, fetch_web_metadata, parse_html_metadata

LOGGER = logging.getLogger("superdeal.browser_enrichment")


def _text(page, selectors: tuple[str, ...]) -> str | None:
    for selector in selectors:
        try:
            value = page.locator(selector).first.text_content(timeout=1200)
            if value and value.strip():
                return value.strip()
        except Exception:
            pass
    return None


def _attr(page, selectors: tuple[str, ...], name: str) -> str | None:
    for selector in selectors:
        try:
            value = page.locator(selector).first.get_attribute(name, timeout=1200)
            if value and value.strip():
                return value.strip()
        except Exception:
            pass
    return None


def _number(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"([\\d,]+(?:\\.\\d+)?)", value)
    if not match:
        return None
    try:
        return int(round(float(match.group(1).replace(",", ""))))
    except ValueError:
        return None


def _discount(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"(\\d{1,3})\\s*%", value)
    return int(match.group(1)) if match else None


def _merchant(host: str) -> str | None:
    host = host.lower().removeprefix("www.")
    known = {
        "amazon.in": "Amazon", "flipkart.com": "Flipkart", "myntra.com": "Myntra",
        "ajio.com": "AJIO", "meesho.com": "Meesho", "tatacliq.com": "Tata CLiQ",
        "nykaa.com": "Nykaa", "croma.com": "Croma", "reliancedigital.in": "Reliance Digital",
    }
    for domain, name in known.items():
        if host == domain or host.endswith("." + domain):
            return name
    if not host:
        return None
    parts = host.split(".")
    label = parts[-2] if len(parts) >= 2 else parts[0]
    return label.replace("-", " ").title() or None


def _useful(metadata: WebMetadata) -> bool:
    return bool(metadata.image_url or metadata.description or metadata.brand or metadata.price or metadata.mrp)


def fetch_browser_metadata(url: str, *, timeout_ms: int = 15000) -> WebMetadata:
    """Follow an affiliate URL in Chromium and extract metadata from the rendered page."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed") from exc

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                locale="en-IN",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/140.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 5000))
            except Exception:
                pass
            metadata = parse_html_metadata(page.content(), source_url=page.url)
            host = urlparse(page.url).hostname or ""
            merchant = _merchant(host)
            title = _text(page, ("h1", "[itemprop='name']"))
            price = _number(_text(page, ("[itemprop='price']", "[data-testid*='price']", "[class*='price']")))
            mrp = _number(_text(page, ("[class*='mrp']", "[class*='original-price']", "[class*='list-price']")))
            discount_pct = _discount(_text(page, ("[class*='discount']", "[class*='saving']")))
            brand = _text(page, ("[itemprop='brand']", "[data-testid*='brand']", "[class*='brand']"))
            image_url = _attr(page, ("[itemprop='image']", "main img"), "src")
            if merchant == "Amazon":
                title = _text(page, ("#productTitle",)) or title
                price = _number(_text(page, (".a-price .a-offscreen", "#corePrice_feature_div .a-offscreen"))) or price
                mrp = _number(_text(page, (".basisPrice .a-offscreen", ".a-text-price .a-offscreen"))) or mrp
                discount_pct = _discount(_text(page, (".savingsPercentage",))) or discount_pct
                brand = _text(page, ("#bylineInfo",)) or brand
                image_url = _attr(page, ("#landingImage", "#imgBlkFront"), "data-old-hires") or _attr(page, ("#landingImage", "#imgBlkFront"), "src") or image_url
            elif merchant == "Flipkart":
                title = _text(page, ("h1 span", "h1")) or title
                price = _number(_text(page, ("div.Nx9bqj", "div._30jeq3"))) or price
                mrp = _number(_text(page, ("div.yRaY8j", "div._3I9_wc"))) or mrp
                discount_pct = _discount(_text(page, ("div.UkUFwK", "div._3Ay6Sb"))) or discount_pct
                brand = _text(page, ("span.G6XhRU", "span.B_NuCI")) or brand
                image_url = _attr(page, ("img.DByuf4", "img._396cs4"), "src") or image_url
            if mrp and price and not discount_pct and mrp > price:
                discount_pct = round((mrp - price) * 100 / mrp)
            metadata = WebMetadata(
                title=title or metadata.title,
                description=metadata.description,
                brand=brand or metadata.brand,
                canonical_url=metadata.canonical_url or page.url,
                image_url=image_url or metadata.image_url,
                price=price or metadata.price,
                mrp=mrp or metadata.mrp,
                merchant=merchant,
                discount_pct=discount_pct,
            )
            if metadata.canonical_url:
                return metadata
            return WebMetadata(
                title=metadata.title,
                description=metadata.description,
                brand=metadata.brand,
                canonical_url=page.url,
                image_url=metadata.image_url,
                price=metadata.price,
                mrp=metadata.mrp,
                merchant=metadata.merchant,
                discount_pct=metadata.discount_pct,
            )
        finally:
            browser.close()


def fetch_product_metadata(url: str) -> WebMetadata:
    """Prefer rendered-browser enrichment, falling back to the existing HTTP logic."""
    try:
        metadata = fetch_browser_metadata(url)
        if metadata.image_url and metadata.title and metadata.price:
            return metadata
        try:
            fallback = fetch_web_metadata(url)
        except Exception as exc:
            LOGGER.info("HTTP metadata supplement failed: %s", exc)
            return metadata
        return WebMetadata(
            title=metadata.title or fallback.title,
            description=metadata.description or fallback.description,
            brand=metadata.brand or fallback.brand,
            canonical_url=metadata.canonical_url or fallback.canonical_url,
            image_url=metadata.image_url or fallback.image_url,
            price=metadata.price or fallback.price,
            mrp=metadata.mrp or fallback.mrp,
            merchant=metadata.merchant or fallback.merchant,
            discount_pct=metadata.discount_pct or fallback.discount_pct,
        )
    except Exception as exc:
        LOGGER.warning("Browser enrichment failed; using HTTP fallback: %s", exc)
    return fetch_web_metadata(url)
