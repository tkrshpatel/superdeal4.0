import pytest

from superdeal.affiliate import EarnKaroProvider, build_affiliate_url, normalize_source_url


def test_normalize_source_url():
    assert normalize_source_url("HTTPS://WWW.Amazon.IN/p/123?tag=x#section") == "https://www.amazon.in/p/123?tag=x"


def test_invalid_url_rejected():
    with pytest.raises(ValueError):
        normalize_source_url("amazon.in/p/123")


def test_affiliate_url_requires_explicit_provider_output():
    assert build_affiliate_url("https://AMAZON.IN/p/123") is None
    assert build_affiliate_url(
        "https://amazon.in/p/123",
        "https://example.com/track?url=https%3A%2F%2Famazon.in%2Fp%2F123",
    ) == "https://example.com/track?url=https%3A%2F%2Famazon.in%2Fp%2F123"


def test_earnkaro_provider_accepts_generated_link():
    link = EarnKaroProvider().attach_link(
        "https://amazon.in/p/123",
        "https://earnkaro.com/redirect/example",
    )
    assert link.provider == "earnkaro"
    assert link.source_url == "https://amazon.in/p/123"
    assert link.affiliate_url == "https://earnkaro.com/redirect/example"


def test_earnkaro_provider_rejects_invalid_link():
    with pytest.raises(ValueError):
        EarnKaroProvider().attach_link("https://amazon.in/p/123", "not-a-url")
