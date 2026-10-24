import sys
from pathlib import Path
from copy import deepcopy
from datetime import datetime, timezone
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from superdeal_replay_coupon import choose_saved_deal, replay_response
from affiliate_link_ids import restore_affiliate_urls
from backend import Backend


def fixture_db():
    mm=pytest.importorskip('mongomock')
    db=mm.MongoClient().replay_test
    product={'product_name':'Phone','brand':None,'ecommerce_platform':'Amazon','deal_price':12999,
             'original_price':None,'discount_percentage':None,'affiliate_urls':['https://ek.example/a'],'confidence':90,'issues':[]}
    db.ek_raw.insert_one({'raw_id':'original','response_text':'Phone at 12999\nhttps://ek.example/a\nApply coupon code SAVE100 at checkout', 'created_at':datetime.now(timezone.utc)})
    db.pipeline_status.insert_one({'raw_id':'original','status':'PUBLISHED','publication_id':'pub','products_published':1})
    db.fact_table.insert_one({'raw_id':'original','publication_id':'pub','offer_index':0,'product':product})
    return db


def test_selects_source_backed_coupon_without_writing():
    db=fixture_db()
    before=list(db.fact_table.find())
    result=choose_saved_deal(db)
    assert result['terms']['coupon_codes']==['SAVE100']
    assert list(db.fact_table.find())==before


def test_replay_passes_normal_validator_and_preserves_links_prices():
    candidate=choose_saved_deal(fixture_db())
    original=deepcopy(candidate)
    response=replay_response(candidate,'12345678')
    restored=restore_affiliate_urls(response,candidate['saved']['response_text'])
    product=Backend.validate(restored,candidate['saved']['response_text'])['products'][0]
    assert product['product_name']=='[ARCHIVED PREVIEW 12345678] Phone'
    assert product['affiliate_urls']==candidate['fact']['product']['affiliate_urls']
    assert product['deal_price']==12999
    assert candidate==original


def test_unpublished_or_incomplete_messages_are_not_replayed():
    db=fixture_db()
    db.pipeline_status.update_one({}, {'$set':{'status':'FAILED'}})
    assert choose_saved_deal(db) is None


def test_no_supported_terms_means_no_preview():
    db=fixture_db()
    db.ek_raw.update_one({}, {'$set':{'response_text':'Phone at 12999\nhttps://ek.example/a'}})
    assert choose_saved_deal(db) is None


def test_mixed_product_message_is_not_auto_replayed():
    db=fixture_db()
    db.pipeline_status.update_one({}, {'$set':{'products_published':2}})
    assert choose_saved_deal(db) is None
