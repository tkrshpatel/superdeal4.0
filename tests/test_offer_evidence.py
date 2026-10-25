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

@pytest.mark.parametrize('pct,kind,expected',[(75,'exact',False),(75.1,'exact',True),(80,'up_to',False),(100,'exact',True)])
def test_hot_uses_verified_exact_discount(pct,kind,expected):
    from offer_evidence import is_hot
    assert is_hot({'discount_pct':pct,'discount_kind':kind}) is expected

def test_abbreviated_currency_is_not_misread_as_a_small_price():
    assert resolve('Price ₹2k')['current_price'] is None

def test_advertised_up_to_remains_separate_when_exact_price_pair_is_available():
    f=resolve('Price ₹500\nMRP ₹1000\nUp to 80% off')
    assert f['discount_pct']==50 and f['discount_kind']=='calculated'
    assert f['advertised_discount']=={'value':80,'kind':'up_to'}

@pytest.mark.parametrize('text',['Effective price ₹499','Price ₹499 after cashback','USD price 499','Price $499','Buy 1 get 1 free'])
def test_conditional_or_foreign_prices_are_not_base_inr_values(text):
    assert resolve(text)['current_price'] is None

@pytest.mark.parametrize('text',['Save ₹500','₹500 off','Savings Rs. 500'])
def test_stated_savings_never_become_a_selling_price(text):
    f=resolve(text)
    assert f['current_price'] is None and f['mrp'] is None
    assert f['stated_savings']==500

def test_source_price_and_stated_savings_do_not_invent_mrp():
    f=resolve('Price ₹1000; Save ₹500')
    assert (f['current_price'],f['mrp'],f['stated_savings'])==(1000,None,500)

def test_conditional_rupee_benefit_stays_separate():
    f=resolve('HDFC card ₹500 off')
    assert f['current_price'] is None and f['stated_savings'] is None
    assert f['conditional_offers'][0]['label']=='Bank offer: ₹500'

def test_indian_currency_grouping_is_preserved():
    f=resolve('Price ₹1,29,999; MRP ₹1,49,999')
    assert f['current_price']==129999 and f['mrp']==149999


@pytest.mark.parametrize('suffix',[' + Apply Coupon',' + Use code SAVE',' + Collect coupon',' + Extra 10% off with card'])
def test_headline_discount_is_not_swallowed_by_a_separate_coupon_clause(suffix):
    f=resolve('Amazon : Up to 52% Off on Eha Pots & Plants Starting @419'+suffix)
    assert f['discount_pct']==52 and f['discount_kind']=='up_to'
    assert f['starting_price']==419 and f['current_price'] is None
    from offer_evidence import is_hot
    assert not is_hot(f)

def test_direct_coupon_discount_is_still_conditional():
    f=resolve('Apply coupon for up to 52% off')
    assert f['discount_pct'] is None
    assert f['conditional_offers'][0]['label']=='Coupon offer: Up to 52% off'

def test_starting_price_never_becomes_exact_price():
    f=resolve('Starting at ₹419')
    assert f['starting_price']==419 and f['current_price'] is None

def test_version_one_saved_facts_are_recovered_with_the_updated_parser():
    db=mongomock.MongoClient().db
    raw,oid=ObjectId(),ObjectId()
    db.ek_raw.insert_one({'raw_id':raw,'response_text':'Amazon : Up to 52% Off on Eha Pots & Plants Starting @419 + Apply Coupon\n'+LINK})
    doc={'_id':oid,'raw_id':raw,'publication_id':'pub','offer_index':0,'product':product(),
         'offer_facts':{'version':1,'current_price':None,'mrp':None,'discount_pct':None,'discount_kind':None}}
    db.fact_table.insert_one(doc)
    fields=Backend(db)._offer_fields(doc)
    assert fields['offer_facts']['version']==9
    assert fields['offer_facts']['discount_pct']==52
    assert db.fact_table.find_one({})['offer_facts']['version']==1


@pytest.mark.parametrize('text', [
    'Headphones @252', 'Headphones @ 252 only', 'Headphones @₹252',
    'Headphones Rs 252 only', 'Headphones Rs.252 only', 'Headphones ₹252 only',
    'Headphones INR 252 only', 'Headphones @252; 50% off',
])
def test_message_price_precedes_browser_price(text):
    f=resolve(text,{LINK:{'price':500,'price_source':'json_ld'}})
    assert f['current_price']==252
    assert f['_sources']['current_price']=='earnkaro'

@pytest.mark.parametrize('text', ['Headphones', '50% off', '₹200 off'])
def test_browser_price_is_used_when_source_has_no_selling_price(text):
    f=resolve(text,{LINK:{'price':500,'price_source':'json_ld'}})
    assert f['current_price']==500
    assert f['_sources']['current_price']=='browser'

def test_version_two_price_is_recovered_from_saved_message():
    db=mongomock.MongoClient().db
    raw=ObjectId()
    db.ek_raw.insert_one({'raw_id':raw,'response_text':'Headphones @252\n'+LINK})
    doc={'raw_id':raw,'publication_id':'price-recovery','offer_index':0,'product':product(),
         'offer_facts':{'version':2,'current_price':500}}
    db.fact_table.insert_one(doc)
    fields=Backend(db)._offer_fields(doc)
    assert fields['deal_price']==252
    assert fields['offer_facts']['version']==9


def test_orient_effective_price_with_three_colour_links():
    urls=['https://amzn-to.co/M6St5X','https://amzn-to.co/o0bCYM','https://amzn-to.co/VQYhTS']
    text='52% OFF: Orient Electric Ceiling Fans @ ₹1,255 [Effective Price] Apply 7% Coupon • Brown: '+urls[0]+' • White: '+urls[1]+' • Blue: '+urls[2]
    products=[product(u) for u in urls]
    facts=resolve_offers(text,products,{u:{'price':1500,'price_source':'json_ld'} for u in urls})
    assert all(f['effective_price']==1255 for f in facts)
    assert all(f['current_price']==1500 for f in facts)
    assert all(f['mrp'] is None for f in facts)
    assert all(any('7% off' in o['label'] for o in f['conditional_offers']) for f in facts)
    assert public_facts(facts[0])['effective_price']==1255

def test_distinct_products_do_not_share_headline_price():
    a,b='https://affiliate.example/a','https://affiliate.example/b'
    facts=resolve_offers('Fan @1255 [Effective Price] '+a+' • Headphones: '+b,[product(a),product(b)])
    assert all(f['effective_price'] is None for f in facts)

def test_explicit_effective_price_is_preserved_without_becoming_base_price():
    f=resolve('Effective price ₹499')
    assert f['effective_price']==499
    assert f['current_price'] is None


def test_price_url_rows_split_model_group_and_keep_each_price():
    from offer_evidence import split_priced_products
    urls=['https://amazon.in/dp/B0CGQ834KW?tag=test','https://amazon.in/dp/B0CZNPGM9W?tag=test','https://amazon.in/dp/B0C73X2JQR?tag=test']
    text='Upto 50% Off On Crompton 1HP Water Pumps + Bank Offer\n\n'+'\n'.join(str(p)+' : '+u for p,u in zip([4099,3699,4582],urls))
    grouped={**product(),'affiliate_urls':urls}
    products=split_priced_products(text,[grouped])
    assert [p['affiliate_urls'] for p in products]==[[u] for u in urls]
    facts=resolve_offers(text,products)
    assert [f['current_price'] for f in facts]==[4099,3699,4582]
    assert all(f['discount_pct']==50 and f['discount_kind']=='up_to' for f in facts)
    assert grouped['affiliate_urls']==urls

def test_incomplete_price_rows_do_not_split_or_borrow_price():
    from offer_evidence import split_priced_products, priced_link_rows
    text='4099 : '+LINK+'\nUnknown price: https://affiliate.example/b'
    assert priced_link_rows(text)=={}
    p={**product(),'affiliate_urls':[LINK,'https://affiliate.example/b']}
    assert split_priced_products(text,[p])==[p]


def test_led_pack_rows_have_separate_prices_and_source_option_names():
    from offer_evidence import split_priced_products
    urls=['https://amzn-to.co/Nq81sm','https://amzn-to.co/jtgDuz','https://amzn-to.co/y90vGU']
    labels=['Pack of 1 (20W) | 4 feet','Pack of 1 (24W)','Pack of 2 (36W) | 4 feet']
    text='Grab : Upto 83% OFF Crompton LED Batten\n\n'+'\n'.join(label+' @'+str(price)+' : '+url for label,price,url in zip(labels,[129,190,599],urls))
    grouped={**product(),'product_name':'Crompton LED Batten','affiliate_urls':urls}
    products=split_priced_products(text,[grouped])
    assert len(products)==3
    assert all(label in p['product_name'] for label,p in zip(labels,products))
    assert [p['affiliate_urls'] for p in products]==[[u] for u in urls]
    facts=resolve_offers(text,products)
    assert [f['current_price'] for f in facts]==[129,190,599]
    assert all(f['discount_pct']==83 and f['discount_kind']=='up_to' for f in facts)
    assert split_priced_products(text,products)==products

def test_option_measurements_never_replace_the_explicit_price():
    from offer_evidence import split_priced_products
    urls=[LINK,'https://affiliate.example/b']
    text='LED Battens\nPack of 2 (36W) | 4 feet @599 : '+urls[0]+'\nPack of 1 (20W) @129 : '+urls[1]
    facts=resolve_offers(text,split_priced_products(text,[{**product(),'affiliate_urls':urls}]))
    assert [f['current_price'] for f in facts]==[599,129]


@pytest.mark.parametrize('separator',['  ','\n'])
def test_realme_inline_prices_with_sentence_punctuation(separator):
    from offer_evidence import split_priced_products
    a,b='https://fkrt.co/6a6jJP','https://fkrt.co/YXyJtT'
    text='Price Drop : realme P4R 5G (4GB | 128GB) at 18749. '+a+separator+'6GB | 128GB at 21349 : '+b+' *COD Available | Buy Fast. *Price May Increase Anytime'
    grouped={**product(),'product_name':'realme P4R 5G','affiliate_urls':[a,b]}
    facts=resolve_offers(text,split_priced_products(text,[grouped]))
    assert [f['current_price'] for f in facts]==[18749,21349]
    assert all(f['mrp'] is None for f in facts)

@pytest.mark.parametrize('text,value',[('Phone at 18749.',18749),('Phone @252.',252),('Phone Rs 252 only.',252),('Phone at 18749.50.',18749.5)])
def test_sentence_ending_period_does_not_hide_a_price(text,value):
    assert resolve(text)['current_price']==value

def test_incomplete_decimal_is_not_silently_truncated():
    assert resolve('Phone at 18749.999')['current_price'] is None


@pytest.mark.parametrize('phrase',['Starts Rs.262','Starts at Rs.262','Starts from ₹262','Starting Rs.262','Start at ₹262'])
def test_starting_price_wording_variants(phrase):
    f=resolve("Myntra: Upto 86% Off on Roadster Men's Shirts "+phrase)
    assert f['starting_price']==262
    assert f['current_price'] is None
    assert f['discount_pct']==86 and f['discount_kind']=='up_to'


def test_standalone_price_and_separate_bare_card_saving():
    f=resolve('86700\n\n11000 off Using Card')
    assert f['current_price']==86700
    assert f['mrp'] is None and f['discount_pct'] is None
    assert f['conditional_offers']==[{'label':'Bank offer: ₹11000','kind':'conditional_amount'}]

@pytest.mark.parametrize('text,value',[('86,700',86700),('86700',86700),('86700.50',86700.5)])
def test_standalone_amount_price(text,value):
    assert resolve(text)['current_price']==value

def test_card_benefit_alone_is_not_a_price():
    f=resolve('11000 off Using Card')
    assert f['current_price'] is None
    assert f['conditional_offers'][0]['label']=='Bank offer: ₹11000'

def test_conflicting_standalone_prices_remain_ambiguous():
    f=resolve('86700\n85700')
    assert f['current_price'] is None
    assert 'AMBIGUOUS_SOURCE_PRICE' in f['_conflicts']
