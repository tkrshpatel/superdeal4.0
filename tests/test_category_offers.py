from category_offers import category_context, normalize_category_products
from offer_evidence import resolve_offers

def test_tokyo_talkies_categories_share_brand_and_discount_without_prices():
    labels=['Dresses','Jeans','Tops','Sweatshirts','Sweaters','Shirt','Co-Ords','Trousers']
    urls=['https://example.com/'+str(i) for i in range(8)]
    text="Myntra Loot : Upto 90% Off On Tokyo Talkies Women's Clothing\n\n"+'\n'.join(label+(' ; ' if i==3 else ' : ')+url for i,(label,url) in enumerate(zip(labels,urls)))
    grouped={'product_name':'Clothing','affiliate_urls':urls,'deal_price':None}
    products=normalize_category_products(text,[grouped])
    assert [p['product_name'] for p in products]==['Tokyo Talkies '+label for label in labels]
    facts=resolve_offers(text,products)
    assert all(f['discount_pct']==90 and f['discount_kind']=='up_to' for f in facts)
    assert all(f['current_price'] is None for f in facts)
    browser={url:{'price':499,'price_source':'json_ld'} for url in urls}
    assert all(f['current_price']==499 for f in resolve_offers(text,products,browser))
    assert grouped['product_name']=='Clothing'

def test_product_list_without_source_brand_context_is_not_renamed():
    assert category_context('Up to 90% off\n\nDresses: https://example.com/a\nJeans: https://example.com/b')=={}
