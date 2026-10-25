"""Real publication and API adaptation of source-only discount evidence."""
import json
import os
from uuid import uuid4
from pymongo import MongoClient
from backend import Backend
from api import _legacy_deal
from public_presentation import public_payload

def test_discount_only_publication_and_private_evidence():
    client=MongoClient(os.getenv('MONGODB_URI','mongodb://127.0.0.1:27017/?replicaSet=rs0'),serverSelectionTimeoutMS=5000)
    db=client['superdeal_test_offer_evidence_'+uuid4().hex]
    link='https://affiliate.example/keep?tag=original&token=exact'
    try:
        backend=Backend(db,image_scraper=lambda *args,**kwargs:None)
        backend.setup()
        backend.converter=lambda _: {'response_text':'Headphones\n60% off\n'+link,'response_payload':{'data':'Headphones\n60% off\n'+link}}
        backend.llm=lambda _: {'products':[{'product_name':'Headphones','brand':'Sony','ecommerce_platform':'Amazon',
            'deal_price':1,'original_price':999999,'discount_percentage':99,'link_ids':['LINK_001'],'confidence':95,'issues':[]}],
            'unassigned_link_ids':[],'message_issues':[],'analysis_summary':''}
        raw_id=backend.ingest('@private_test_channel','1','Headphones\n'+link)
        assert backend.process(raw_id)==1
        doc=db.fact_table.find_one({'raw_id':raw_id})
        assert doc['product']['deal_price'] is None and doc['product']['original_price'] is None
        assert doc['product']['discount_percentage']==60
        assert doc['product']['affiliate_urls']==[link]
        assert doc['offer_facts']['_sources']['discount']=='earnkaro'
        deal=backend.published_offer_by_id(str(doc['_id']))
        public=public_payload(_legacy_deal(deal,backend.public_metadata(deal['id'])))
        assert public['discount_pct']==60 and public['hot'] is False
        assert public['offer_facts']['discount_kind']=='exact'
        assert public['affiliate_url']==link
        assert 'earnkaro' not in json.dumps(public,default=str).lower()
        assert '_sources' not in json.dumps(public,default=str)
    finally:
        client.drop_database(db.name);client.close()
