"""Offer scenario matrix; no network, provider calls or LLM price evidence."""
from copy import deepcopy
import pytest
import mongomock
from bson import ObjectId
from offer_evidence import resolve_offers, public_facts
from public_presentation import public_payload
from backend import Backend

LINK='https://affiliate.example/a'
def product(link=LINK):
    return {'product_name':'Headphones','affiliate_urls':[link],'deal_price':1,'original_price':999999,'discount_percentage':99}
def resolve(text,research=None):
    return resolve_offers(text+'\n'+LINK,[product()],research)[0]

@pytest.mark.parametrize('text,price,mrp,pct,kind',[
    ('Price: ₹400\nMRP: ₹1000',400,1000,60,'calculated'),
    ('Price: Rs. 400\nFlat 60% OFF',400,None,60,'exact'),
    ('60% off',None,None,60,'exact'),
    ('Up to 60% off',None,None,60,'up_to'),
    ('Upto 70% discount',None,None,70,'up_to'),
    ('Discount: 55%',None,None,55,'exact'),
    ('Save 55%',None,None,55,'exact'),
    ('Price: ₹99',99,None,None,None),
    ('At ₹400 (MRP ₹1000)',400,1000,60,'calculated'),
    ('MRP: ₹1000',None,None,None,None),
    ('No price information',None,None,None,None),
    ('0% off',None,None,None,None),
    ('160% off',None,None,None,None),
    ('20–60% off',None,None,None,None),
    ('Price: ₹400\nMRP ₹300',400,None,None,None),
])
def test_source_scenario_matrix(text,price,mrp,pct,kind):
    f=resolve(text)
    assert (f['current_price'],f['mrp'],f['discount_pct'],f['discount_kind'])==(price,mrp,pct,kind)

@pytest.mark.parametrize('text,label',[
    ('Use coupon SAVE for 60% off','Coupon offer: 60% off'),
    ('HDFC card 20% off','Bank offer: 20% off'),
    ('Extra 10% off','Additional offer: 10% off'),
    ('Up to 15% cashback','Cashback: Up to 15% cashback'),
])
def test_conditions_are_not_base_discounts(text,label):
    f=resolve(text)
    assert f['discount_pct'] is None and f['current_price'] is None
    assert f['conditional_offers'][0]['label']==label

def test_source_beats_browser_and_llm_without_mutation():
    products=[product()];before=deepcopy(products)
    research={LINK:{'price':700,'price_source':'json_ld','mrp':2000,'mrp_source':'product_page'}}
    f=resolve_offers('Price ₹400\nMRP ₹1000\n'+LINK,products,research)[0]
    assert f['current_price']==400 and f['mrp']==1000 and f['discount_pct']==60
    assert products==before
    assert 'BROWSER_PRICE_DISAGREES' in f['_conflicts']

def test_verified_browser_fills_only_missing_values():
    research={LINK:{'price':400,'price_source':'json_ld','mrp':1000,'mrp_source':'product_page'}}
    f=resolve('Headphones',research)
    assert (f['current_price'],f['mrp'],f['discount_pct'])==(400,1000,60)
    assert resolve('Headphones',{LINK:{'price':400,'mrp':1000}})['discount_pct'] is None

def test_exact_source_discount_outweighs_conflicting_borrowed_mrp():
    f=resolve('Price ₹400\n60% off',{LINK:{'mrp':2000,'mrp_source':'product_page'}})
    assert (f['current_price'],f['mrp'],f['discount_pct'],f['discount_kind'])==(400,None,60,'exact')
    assert 'BORROWED_PAIR_DISAGREES' in f['_conflicts']

def test_conflicting_source_percentage_uses_clear_source_price_pair_and_logs():
    f=resolve('Price ₹500\nMRP ₹1000\n60% off')
    assert f['discount_pct']==50 and f['discount_kind']=='calculated'
    assert 'SOURCE_DISCOUNT_DISAGREES' in f['_conflicts']

def test_ambiguous_source_prices_do_not_get_silently_overridden():
    f=resolve('Price ₹400\nPrice ₹500',{LINK:{'price':600,'price_source':'json_ld'}})
    assert f['current_price'] is None and 'AMBIGUOUS_SOURCE_PRICE' in f['_conflicts']

def test_product_scoping_and_shared_link_ambiguity():
    second='https://affiliate.example/b'
    p=[product(),product(second)]
    f=resolve_offers('Headphones 60% off\n'+LINK+'\n\nShoes up to 70% off\n'+second,p)
    assert [x['discount_pct'] for x in f]==[60,70]
    assert [x['discount_kind'] for x in f]==['exact','up_to']
    assert all(x['discount_pct'] is None for x in resolve_offers('60% off\n'+LINK,[product(),product()]))

def test_private_provenance_and_conflicts_never_reach_public_json():
    f=resolve('60% off')
    assert '_sources' not in public_facts(f)
    payload=public_payload({'offer_facts':{**f,'source':'earnkaro','raw_text':'@channel','unexpected':'private'}})
    assert set(payload['offer_facts'])<=set(public_facts(f))
    assert 'earnkaro' not in str(payload).lower() and '@channel' not in str(payload)

def test_existing_fact_recovers_discount_from_saved_converted_message_without_writes():
    db=mongomock.MongoClient().db
    raw,oid=ObjectId(),ObjectId()
    p=product()
    db.ek_raw.insert_one({'raw_id':raw,'response_text':'60% off\n'+LINK})
    doc={'_id':oid,'raw_id':raw,'publication_id':'pub','offer_index':0,'product':p}
    db.fact_table.insert_one(doc)
    before=deepcopy(db.fact_table.find_one({}))
    fields=Backend(db)._offer_fields(doc)
    assert fields['discount_percentage']==60
    assert fields['deal_price'] is None and fields['original_price'] is None
    assert fields['offer_facts']['discount_kind']=='exact'
    assert db.fact_table.find_one({})==before
