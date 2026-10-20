import copy
from image_enrichment import rank_candidates, enrich_products

def test_candidate_rank_chooses_product_not_promo():
    c = [{'url':'https://asset21.ckassets.com/resources/image/stores/ogimage/flipkart.png', 'rank':150}, {'url':'https://rukminim2.flixcart.com/image/612/612/iphone-case.jpeg', 'rank':95, 'label':'iPhone case'}]
    assert rank_candidates(c, 'https://www.flipkart.com/p/item', 'iPhone case') == ['https://rukminim2.flixcart.com/image/612/612/iphone-case.jpeg']

def test_generic_unrelated_images_not_accepted():
    c=[{'url':'https://example.com/hero-sale.jpg','rank':40}, {'url':'https://example.com/red-smartwatch-product.jpg','rank':40}]
    assert rank_candidates(c,'https://example.com/item','Red Smartwatch') == ['https://example.com/red-smartwatch-product.jpg']

def test_product_identity_immutable():
    products=[{'product_name':'First item','affiliate_urls':['https://merchant.example/a'],'deal_price':123}, {'product_name':'Second item','affiliate_urls':['https://merchant.example/b'],'deal_price':456}]
    before=copy.deepcopy(products)
    calls=[]
    def scraper(links, detailed=False, product_name=''):
        calls.append((links,product_name))
        return {'image_url':'https://images.example.com/first-item.jpeg', 'reason':'FOUND'}
    result=enrich_products('https://merchant.example/a https://merchant.example/b',products,scraper=scraper)
    assert products==before
    assert len(result)==2 and len(calls)==2
    assert calls[0][1]=='First item' and calls[1][1]=='Second item'

def test_ambiguous_source_not_scraped():
    products=[{'product_name':'First', 'affiliate_urls':['https://earn.example/a']},{'product_name':'Second','affiliate_urls':['https://earn.example/b']}]
    def scraper(*args,**kw): raise AssertionError('must not run')
    out=enrich_products('https://merchant.example/unknown',products,scraper=scraper)
    assert all(x['status']=='PLACEHOLDER' for x in out)
