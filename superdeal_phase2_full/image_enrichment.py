"""Synchronous, read-only enrichment of validated SuperDeal products.

Never mutates products, product order or affiliate URLs. Source links come exclusively
from the ORIGINAL Telegram message, never from EarnKaro-only URLs.
"""
from __future__ import annotations

import ipaddress
import inspect
import re
import socket
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, urlunsplit

URL_RE = re.compile(r'https?://[^\s<>"\']+')

def urls(text):
    return set(u.rstrip('.,;!?)\\]}>') for u in URL_RE.findall(text or ''))

PLACEHOLDER_IMAGE = '/superdeal-placeholder.svg'
BAD_IMAGE = re.compile(r'(?:^|[/_\-.])(logo|sprite|favicon|placeholder|pixel|tracking|badge|icon|avatar|loader|banner)(?:[/_\-.]|$)', re.I)
PUBLIC_SUFFIX_BLOCK = ('localhost', 'localhost.localdomain')


def safe_url(value, domains=None):
    """Conservatively validate public HTTPS URL form, optionally a domain allowlist."""
    if not isinstance(value, str) or len(value) > 3000 or any(c in value for c in '\r\n\\\t'):
        return False
    try:
        p = urlsplit(value)
        if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
            return False
        host = p.hostname.lower().rstrip('.')
        if host in PUBLIC_SUFFIX_BLOCK or host.endswith(('.local', '.internal', '.localhost', '.test', '.invalid')):
            return False
        if '.' not in host or not re.fullmatch(r'[a-z0-9.-]+', host):
            return False
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            pass
        return domains is None or any(host == d or host.endswith('.' + d) for d in domains)
    except (ValueError, TypeError):
        return False


def _public_dns(host):
    """Reject hosts resolving to non-public IPs (best-effort SSRF protection)."""
    try:
        addresses = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        return bool(addresses) and all(ipaddress.ip_address(info[4][0]).is_global for info in addresses)
    except (OSError, ValueError):
        return False


def normalize_image_url(url):
    """Normalize Flipkart's unresolved OG template without touching product links."""
    if not isinstance(url, str):
        return url
    try:
        host = (urlsplit(url).hostname or '').lower()
    except ValueError:
        return url
    if host == 'flixcart.com' or host.endswith('.flixcart.com'):
        return url.replace('{@width}', '800').replace('{@height}', '800')
    return url


def source_urls(raw_text, affiliate_urls, merchant=None, *, all_products=None):
    """Choose only unambiguous original Telegram links for one product.

    A single raw link may be used for a single product. With multiple products,
    only an exact URL belonging to this product and no other product qualifies.
    Never derive an original link from an EarnKaro redirect.
    """
    raw = [u for u in sorted(urls(raw_text)) if safe_url(u)]
    if not raw:
        return []
    if all_products is None:
        # Legacy API: prefer exact matching; single source is otherwise unambiguous.
        matched = [u for u in raw if u in set(affiliate_urls or [])]
        return matched if len(matched) == 1 else (raw if len(raw) == 1 else [])
    if len(all_products) == 1:
        return raw if len(raw) == 1 else []
    matching = [u for u in raw if u in set(affiliate_urls or [])]
    if len(matching) != 1:
        return []
    candidate = matching[0]
    owners = sum(candidate in set(p.get('affiliate_urls') or []) for p in all_products)
    return [candidate] if owners == 1 else []


def _image_candidates(page):
    """Product JSON-LD, hero images, OG/Twitter meta, and generic large images."""
    return page.evaluate('''() => {
      const out = [];
      const add = (v, rank) => {
        if (typeof v === 'string' && v.trim()) out.push({url:v.trim(), rank});
        else if (Array.isArray(v)) v.forEach(x => add(x, rank));
        else if (v && typeof v === 'object') add(v.url || v.contentUrl, rank);
      };
      for (const node of document.querySelectorAll('script[type="application/ld+json"]')) {
        try {
          const walk = obj => {
            if (Array.isArray(obj)) return obj.forEach(walk);
            if (!obj || typeof obj !== 'object') return;
            const type = Array.isArray(obj['@type']) ? obj['@type'] : [obj['@type']];
            if (type.some(t => typeof t === 'string' && t.toLowerCase() === 'product')) add(obj.image, 110);
            if (obj['@graph']) walk(obj['@graph']);
          };
          walk(JSON.parse(node.textContent));
        } catch (e) {}
      }
      for (const selector of ['#landingImage', '#imgTagWrapperId img', 'img[data-a-dynamic-image]',
           'img[fetchpriority="high"]', 'meta[property="og:image"]', 'meta[name="twitter:image"]']) {
        for (const el of document.querySelectorAll(selector)) {
          add(el.content || el.getAttribute('data-old-hires') || el.currentSrc || el.src,
              selector.startsWith('meta') ? 85 : 95);
        }
      }
      for (const img of document.images) {
        const w = img.naturalWidth || img.width;
        const h = img.naturalHeight || img.height;
        if (w >= 250 && h >= 250) add(img.currentSrc || img.src, 40);
      }
      return out;
    }''')


def candidate_urls(candidates, page_url):
    ranked, seen = [], set()
    for item in candidates:
        if not isinstance(item, dict) or not isinstance(item.get('url'), str):
            continue
        url = normalize_image_url(urljoin(page_url, item['url']))
        if not safe_url(url) or BAD_IMAGE.search(urlsplit(url).path) or url in seen:
            continue
        seen.add(url)
        rank = item.get('rank', 0)
        ranked.append((rank if isinstance(rank, (float, int)) else 0, url))
    return [url for _, url in sorted(ranked, key=lambda x: -x[0])]


def choose_image(candidates, page_url):
    options = candidate_urls(candidates, page_url)
    return options[0] if options else None


def _browser_image_loads(page, image_url):
    """Check actual image load and useful dimensions in the merchant browser."""
    try:
        return bool(page.evaluate('''async url => {
          const img = new Image();
          return await Promise.race([
            new Promise(resolve => {
              img.onload = () => resolve(img.naturalWidth >= 150 && img.naturalHeight >= 150);
              img.onerror = () => resolve(false);
              img.src = url;
            }),
            new Promise(resolve => setTimeout(() => resolve(false), 4500))
          ]);
        }''', image_url))
    except Exception:
        return False


def scrape_image(original_links, *, browser=None, detailed=False):
    """Return URL by default for compatibility, diagnostics with detailed=True.

    Only original raw Telegram links are accepted. A page might fail on blocked
    retailers, so failures are recorded and fallback stays synchronous.
    """
    from playwright.sync_api import sync_playwright
    def result(image=None, reason='NO_IMAGE'):
        value = {'image_url': image, 'reason': reason}
        return value if detailed else image
    if not original_links:
        return result(reason='NO_SOURCE_LINK')
    if browser is None:
        with sync_playwright() as p:
            own = p.chromium.launch(headless=True)
            try:
                return scrape_image(original_links, browser=own, detailed=detailed)
            finally:
                own.close()
    context = browser.new_context(service_workers='block', accept_downloads=False)
    last_reason = 'NO_CANDIDATE'
    checked_hosts = {}
    try:
        def guard(route):
            target = route.request.url
            if not safe_url(target):
                return route.abort()
            host = urlsplit(target).hostname
            if host not in checked_hosts:
                checked_hosts[host] = _public_dns(host)
            if not checked_hosts[host]:
                return route.abort()
            if route.request.resource_type in ('media', 'font', 'websocket'):
                return route.abort()
            return route.continue_()
        context.route('**/*', guard)
        page = context.new_page()
        page.set_default_timeout(8000)
        for link in original_links[:2]:
            if not safe_url(link):
                continue
            try:
                response = page.goto(link, wait_until='domcontentloaded', timeout=20000)
                if not safe_url(page.url):
                    last_reason = 'UNSAFE_REDIRECT'
                    continue
                if response and response.status >= 400:
                    last_reason = 'HTTP_ERROR_' + str(response.status)
                    continue
                candidates = candidate_urls(_image_candidates(page), page.url)
                if not candidates:
                    last_reason = 'NO_CANDIDATE'
                    continue
                for img in candidates[:5]:
                    if _browser_image_loads(page, img):
                        return result(img, 'FOUND')
                last_reason = 'INVALID_IMAGE'
            except Exception as exc:
                last_reason = 'BROWSER_' + type(exc).__name__.upper()
        return result(reason=last_reason)
    finally:
        context.close()


def enrich_products(raw_text, products, *, scraper=None):
    """Create one independent image result per validated product; never modify it."""
    scraper = scraper or scrape_image
    results = []
    for product in products:
        links = source_urls(raw_text, product.get('affiliate_urls', []),
                            product.get('ecommerce_platform'), all_products=products)
        image, reason = None, 'AMBIGUOUS_OR_MISSING_SOURCE_LINK'
        if links:
            try:
                # Retain compatibility with existing injected scraper callables.
                parameters = inspect.signature(scraper).parameters
                raw = scraper(links, detailed=True) if 'detailed' in parameters else scraper(links)
                if isinstance(raw, dict):
                    image = raw.get('image_url')
                    reason = str(raw.get('reason') or 'NO_IMAGE')
                else:
                    image = raw
                    reason = 'FOUND' if image else 'NO_IMAGE'
            except Exception as exc:
                reason = 'SCRAPER_' + type(exc).__name__.upper()
        if image and safe_url(image):
            results.append({'status': 'FOUND', 'image_url': image,
                            'diagnostics': {'reason': 'FOUND'}, 'updated_at': datetime.now(timezone.utc)})
        else:
            results.append({'status': 'PLACEHOLDER', 'image_url': PLACEHOLDER_IMAGE,
                            'diagnostics': {'reason': reason[:100]}, 'updated_at': datetime.now(timezone.utc)})
    return results
