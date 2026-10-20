from superdeal import browser_enrichment
from superdeal.web_enrichment import WebMetadata


def test_browser_first_returns_browser_metadata(monkeypatch):
    expected = WebMetadata(title="Product", image_url="https://merchant.example/image.jpg", price=999)
    monkeypatch.setattr(browser_enrichment, "fetch_browser_metadata", lambda url: expected)

    def fail_http(url):
        raise AssertionError("HTTP fallback should not run")

    monkeypatch.setattr(browser_enrichment, "fetch_web_metadata", fail_http)
    assert browser_enrichment.fetch_product_metadata("https://earnkaro.example/x") == expected


def test_browser_failure_uses_existing_http_fallback(monkeypatch):
    def fail_browser(url):
        raise RuntimeError("browser unavailable")

    expected = WebMetadata(image_url="https://fallback.example/image.jpg")
    monkeypatch.setattr(browser_enrichment, "fetch_browser_metadata", fail_browser)
    monkeypatch.setattr(browser_enrichment, "fetch_web_metadata", lambda url: expected)

    assert browser_enrichment.fetch_product_metadata("https://earnkaro.example/x") == expected


def test_empty_browser_result_uses_existing_http_fallback(monkeypatch):
    monkeypatch.setattr(browser_enrichment, "fetch_browser_metadata", lambda url: WebMetadata())
    expected = WebMetadata(title="Fallback title", image_url="https://fallback.example/image.jpg")
    monkeypatch.setattr(browser_enrichment, "fetch_web_metadata", lambda url: expected)

    assert browser_enrichment.fetch_product_metadata("https://earnkaro.example/x") == expected


def test_incomplete_browser_metadata_is_supplemented_by_http(monkeypatch):
    browser = WebMetadata(title="Rendered product", merchant="Amazon", price=999)
    fallback = WebMetadata(image_url="https://fallback.example/image.jpg", mrp=1999)
    monkeypatch.setattr(browser_enrichment, "fetch_browser_metadata", lambda url: browser)
    monkeypatch.setattr(browser_enrichment, "fetch_web_metadata", lambda url: fallback)

    result = browser_enrichment.fetch_product_metadata("https://earnkaro.example/x")
    assert result.title == "Rendered product"
    assert result.merchant == "Amazon"
    assert result.price == 999
    assert result.mrp == 1999
    assert result.image_url == "https://fallback.example/image.jpg"


def test_merchant_resolution_supports_known_and_generic_domains():
    assert browser_enrichment._merchant("www.myntra.com") == "Myntra"
    assert browser_enrichment._merchant("ajio.com") == "AJIO"
    assert browser_enrichment._merchant("shop.example-store.com") == "Example Store"
