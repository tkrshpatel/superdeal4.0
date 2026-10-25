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
    at=datetime.now(timezone.utc).replace(microsecond=0)
    backend=Backend(db)
    http=None
    thread=None
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
        # Exercise the actual HTTP snapshot/continuation contract as well.
        import threading
        from http.server import ThreadingHTTPServer
        from urllib.request import urlopen
        from urllib.parse import urlencode
        import json
        from api import make_handler
        http=ThreadingHTTPServer(('127.0.0.1',0),make_handler(backend,admin_token='test-only'))
        thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        offset=0;snapshot=None;http_ids=[]
        while True:
            params={'limit':24,'offset':offset,'sort':'newest'}
            if snapshot:params['as_of']=snapshot
            with urlopen(f'http://127.0.0.1:{http.server_port}/deals?'+urlencode(params),timeout=5) as response:
                payload=json.load(response)
            snapshot=snapshot or payload['as_of']
            assert payload['as_of']==snapshot
            http_ids.extend(d['id'] for d in payload['deals'])
            if not payload['has_more']:break
            offset=payload['next_offset']
        # The exact boundary deal may have expired by HTTP request time;
        # all 137 recent deals must still be reachable once each.
        assert len(http_ids)==len(set(http_ids))>=137
    finally:
        if http:
            http.shutdown();thread.join(timeout=3);http.server_close()
        client.drop_database(db.name)
        client.close()
