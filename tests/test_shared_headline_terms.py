from deal_terms import extract_deal_terms

def test_shared_headline_coupon_applies_to_every_product_without_prices():
    urls=['https://example.com/a','https://example.com/b','https://example.com/c','https://example.com/d']
    products=[{'affiliate_urls':[url]} for url in urls]
    text='Amazon: Upto 65% OFF on Elaris Home Decor + APPLY COUPON\n\n'+'\n'.join('Product @799 : '+url for url in urls)
    terms=extract_deal_terms(text,products)
    assert all(t['has_coupon'] for t in terms)
    assert all(any('APPLY COUPON' in line for line in t['instructions']) for t in terms)
    assert all(not any('@799' in line for line in t['source_excerpts']) for t in terms)

def test_product_specific_coupon_is_not_shared():
    a,b='https://example.com/a','https://example.com/b'
    text='Home decor\n\nOwl Apply Coupon OWL20\n'+a+'\n\nPlanter\n'+b
    terms=extract_deal_terms(text,[{'affiliate_urls':[a]},{'affiliate_urls':[b]}])
    assert terms[0]['has_coupon']
    assert terms[1] is None
