"""Current candidate API: safe ranking and immutable source/product mapping.

The old test imported rank_candidates, a helper absent from this implementation.
These checks exercise the shipped candidate_urls API without changing image logic.
"""
import copy
from image_enrichment import candidate_urls, enrich_products


def test_candidate_ranking_rejects_promo_assets():
    candidates=[{'url':'https://assets.example/logo.png','rank':150},
                {'url':'https://images.example/iphone-case.jpeg','rank':95}]
    assert candidate_urls(candidates,'https://shop.example/p')==['https://images.example/iphone-case.jpeg']


def test_candidates_filter_unsafe_and_duplicate_urls_before_ranking():
    candidates=[{'url':'https://127.0.0.1/private.png','rank':200},
                {'url':'javascript:alert(1)','rank':200},
                {'url':'/low.jpg','rank':40},{'url':'/high.jpg','rank':95},
                {'url':'/high.jpg','rank':95}]
    assert candidate_urls(candidates,'https://shop.example/p')==['https://shop.example/high.jpg','https://shop.example/low.jpg']


def test_product_identity_immutable():
    products=[{'product_name':'First item','affiliate_urls':['https://merchant.example/a'],'deal_price':123},
              {'product_name':'Second item','affiliate_urls':['https://merchant.example/b'],'deal_price':456}]
    before=copy.deepcopy(products)
    calls=[]
    def scraper(links,detailed=False):
        calls.append(links)
        return {'image_url':'https://images.example/item.jpeg','reason':'FOUND'}
    result=enrich_products('https://merchant.example/a https://merchant.example/b',products,scraper=scraper)
    assert products==before
    assert calls==[['https://merchant.example/a'],['https://merchant.example/b']]
    assert len(result)==2


def test_ambiguous_source_not_scraped():
    products=[{'product_name':'First','affiliate_urls':['https://earn.example/a']},
              {'product_name':'Second','affiliate_urls':['https://earn.example/b']}]
    def scraper(*args,**kwargs): raise AssertionError('must not run')
    out=enrich_products('https://merchant.example/unknown',products,scraper=scraper)
    assert all(x['status']=='PLACEHOLDER' for x in out)
