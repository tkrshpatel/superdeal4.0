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


def test_generic_collection_labels_without_a_clothing_dictionary():
    text='Store: Up to 70% off on Acme Kitchen Collection + Apply Coupon\n\nStorage Jars: https://example.com/a\nServing Bowls; https://example.com/b'
    c=category_context(text)
    assert c['names']['https://example.com/a']=='Acme Kitchen Collection Storage Jars'
    assert c['discount']==70
    assert c['brand'] is None

def test_price_bearing_rows_stay_with_existing_price_pipeline():
    text='Up to 60% off on Acme Home\n\nPlanter @279: https://example.com/a\nSculpture @799: https://example.com/b'
    products=[{'product_name':'Original name','affiliate_urls':['https://example.com/a','https://example.com/b']}]
    assert normalize_category_products(text,products)==products


def test_puma_primary_link_and_audience_rows_keep_context():
    from offer_evidence import resolve_offers, is_hot
    urls=['https://amzn-to.co/asgO2l','https://amzn-to.co/WVDAlp','https://amzn-to.co/FNpC3v']
    text='Flat 80% Off On PUMA Shoes.\n\n'+urls[0]+'\n\nMen : '+urls[1]+'\nWomen : '+urls[2]
    grouped={'product_name':'Women','brand':'PUMA','affiliate_urls':urls}
    products=normalize_category_products(text,[grouped])
    assert [p['product_name'] for p in products]==['PUMA Shoes',"PUMA Men's Shoes","PUMA Women's Shoes"]
    assert [p['affiliate_urls'] for p in products]==[[u] for u in urls]
    facts=resolve_offers(text,products)
    assert all(f['discount_pct']==80 and f['discount_kind']=='exact' for f in facts)
    assert all(f['current_price'] is None for f in facts)
    assert all(is_hot(f) for f in facts)
    browser={u:{'price':799,'price_source':'json_ld'} for u in urls}
    assert all(f['current_price']==799 for f in resolve_offers(text,products,browser))

def test_published_history_is_not_renamed_or_given_new_terms():
    import mongomock
    from backend import Backend
    from copy import deepcopy
    from bson import ObjectId
    db=mongomock.MongoClient().db
    raw=ObjectId()
    db.ek_raw.insert_one({'raw_id':raw,'response_text':'Flat 80% Off On PUMA Shoes.\n\nhttps://example.com/a\n\nWomen: https://example.com/b'})
    fact={'_id':ObjectId(),'raw_id':raw,'publication_id':'old',
          'product':{'product_name':'Women','affiliate_urls':['https://example.com/b']},
          'offer_facts':{'version':11,'current_price':None,'mrp':None,'discount_pct':None},
          'deal_terms':None}
    db.fact_table.insert_one(fact)
    before=deepcopy(db.fact_table.find_one({}))
    fields=Backend(db)._offer_fields(fact)
    assert 'product_name' not in fields
    assert fields['discount_percentage'] is None
    assert Backend(db)._public_deal_terms(fact) is None
    assert db.fact_table.find_one({})==before
