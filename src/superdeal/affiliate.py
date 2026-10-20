"""Affiliate URL handling and provider contracts.

EarnKaro currently exposes profit-link creation through its logged-in
Make Links workflow in public documentation. No public API endpoint is
assumed here; provider output must be supplied explicitly until an
official integration contract is available.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse, urlunparse


def normalize_source_url(url: str | None) -> str | None:
    """Normalize a source URL for stable storage and comparison."""
    if not url:
        return None
    value = url.strip()
    parsed = urlparse(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("source URL must be an absolute HTTP(S) URL")
    return urlunparse(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, "", parsed.query, "")
    )


def build_affiliate_url(source_url: str | None, affiliate_url: str | None = None) -> str | None:
    """Return only an explicitly supplied provider-generated affiliate URL."""
    if not affiliate_url:
        return None
    return normalize_source_url(affiliate_url)


class AffiliateProvider(Protocol):
    """Contract for a provider that returns a provider-generated link."""

    name: str

    def attach_link(self, source_url: str, provider_url: str) -> "AffiliateLink":
        ...


@dataclass(frozen=True, slots=True)
class AffiliateLink:
    """A validated provider-generated link associated with a source URL."""

    provider: str
    source_url: str
    affiliate_url: str


class EarnKaroProvider:
    """Accept an EarnKaro link created through the documented workflow.

    This adapter deliberately does not automate login, link generation, or
    undocumented endpoints. The returned URL must already have been generated
    by EarnKaro for the supplied merchant URL.
    """

    name = "earnkaro"

    def attach_link(self, source_url: str, provider_url: str) -> AffiliateLink:
        normalized_source = normalize_source_url(source_url)
        normalized_provider = normalize_source_url(provider_url)
        if normalized_source is None or normalized_provider is None:
            raise ValueError("both source and affiliate URLs are required")
        return AffiliateLink(
            provider=self.name,
            source_url=normalized_source,
            affiliate_url=normalized_provider,
        )
