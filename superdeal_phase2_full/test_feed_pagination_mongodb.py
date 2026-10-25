"""Real MongoDB paging over more than 100 committed deals; no external providers."""
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from bson import ObjectId
from pymongo import MongoClient
from backend import Backend

def test_all_pages_share_window_and_exclude_old_unpublished_and_future():
    client=MongoClient(os.getenv('MONGODB_URI','mongodb://127.0.0.1:27017/?replicaSet=rs0'),serverSelectionTimeoutMS=5000)
    db=client['superdeal_test_paging_'+uuid4().hex]
    at=datetime.now(timezone.utc)
    backend=Backend(db)
    try:
        backend.setup()
        for label,date,status,count in [
            ('recent',at-timedelta(hours=1),'PUBLISHED',137),
            ('boundary',at-timedelta(hours=24),'PUBLISHED',1),
            ('old',at-timedelta(hours=24,seconds=1),'PUBLISHED',1),
            ('future',at+timedelta(seconds=1),'PUBLISHED',1),
            ('pending',at-timedelta(hours=1),'PENDING',1)]:
            raw,pub=ObjectId(),uuid4().hex
            db.pipeline_status.insert_one({'raw_id':raw,'publication_id':pub,'status':status,'published_at':date,'products_published':count})
            db.fact_table.insert_many([{'raw_id':raw,'publication_id':pub,'offer_index':i,'product':{
                'product_name':label+' '+str(i),'deal_price':i+1,'affiliate_urls':['https://example.com/'+str(i)]}} for i in range(count)])
        for sort in ('newest','price_asc','price_desc','popular'):
            offset=0; ids=[];names=[]
            while True:
                page=backend.legacy_search(limit=24,offset=offset,at=at,sort=sort)
                assert page['as_of']==at.isoformat()
                ids.extend(d['id'] for d in page['items'])
                names.extend(d['product_name'] for d in page['items'])
                if not page['has_more']:break
                assert page['next_offset']>offset
                offset=page['next_offset']
            assert len(ids)==len(set(ids))==138
            assert any(n.startswith('boundary') for n in names)
            assert all(n.startswith(('recent','boundary')) for n in names)
        assert backend.legacy_search(limit=24,q='recent 136',at=at)['items'][0]['product_name']=='recent 136'
    finally:
        client.drop_database(db.name)
        client.close()
