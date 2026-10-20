from superdeal.web_enrichment import parse_html_metadata


def test_parse_product_metadata():
    html = """
    <html><head>
      <title>Atomberg Efficio Exhaust Fan</title>
      <meta property="og:title" content="Atomberg Efficio Exhaust Fan 200mm">
      <meta property="og:image" content="/images/fan.jpg">
      <meta property="og:url" content="https://example.com/product/fan">
      <meta property="product:price:amount" content="1499">
      <link rel="canonical" href="https://example.com/product/fan?ref=deal">
    </head></html>
    """
    result = parse_html_metadata(html, source_url="https://example.com/deal")
    assert result.title == "Atomberg Efficio Exhaust Fan"
    assert result.image_url == "https://example.com/images/fan.jpg"
    assert result.canonical_url == "https://example.com/product/fan?ref=deal"
    assert result.price == 1499


def test_missing_metadata_is_safe():
    result = parse_html_metadata("<html><body>Nothing useful</body></html>", source_url="https://example.com")
    assert result == result.__class__()


def test_parse_json_ld_product_metadata():
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@type":"Product","name":"Noise Buds X","description":"Wireless earbuds",
     "brand":{"@type":"Brand","name":"Noise"},"image":["/buds.jpg"],
     "offers":{"@type":"Offer","price":"1299","highPrice":"2999"}}
    </script>
    </head></html>
    """
    result = parse_html_metadata(html, source_url="https://shop.example/p/1")
    assert result.title == "Noise Buds X"
    assert result.description == "Wireless earbuds"
    assert result.brand == "Noise"
    assert result.image_url == "https://shop.example/buds.jpg"
    assert result.price == 1299
    assert result.mrp == 2999


def test_parse_image_metadata_fallbacks():
    twitter = parse_html_metadata(
        '<meta name="twitter:image" content="https://cdn.example/twitter.jpg">',
        source_url="https://shop.example/p/1",
    )
    assert twitter.image_url == "https://cdn.example/twitter.jpg"

    itemprop = parse_html_metadata(
        '<meta itemprop="image" content="/images/schema.jpg">',
        source_url="https://shop.example/p/1",
    )
    assert itemprop.image_url == "https://shop.example/images/schema.jpg"

    og_url = parse_html_metadata(
        '<meta property="og:image:url" content="//cdn.example/og.jpg">',
        source_url="https://shop.example/p/1",
    )
    assert og_url.image_url == "https://cdn.example/og.jpg"
