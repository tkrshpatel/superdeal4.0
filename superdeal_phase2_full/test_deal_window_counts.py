from datetime import datetime,timedelta,timezone
import pytest
from backend import Backend


def test_counts_cover_all_facts_not_page_and_require_committed_publication():
    mm=pytest.importorskip('mongomock')
    db=mm.MongoClient(tz_aware=True).counts
    at=datetime(2026,10,25,12,tzinfo=timezone.utc)
    def add(raw,minutes,count,status='PUBLISHED',fact_pub='pub',status_pub='pub'):
        db.pipeline_status.insert_one({'raw_id':raw,'publication_id':status_pub,'status':status,'published_at':at-timedelta(minutes=minutes)})
        for i in range(count):
            db.fact_table.insert_one({'raw_id':raw,'publication_id':fact_pub,'offer_index':i,'product':{'product_name':str(i)}})
    add('fresh',10,20)
    add('older',120,246)
    add('expired',1441,5)
    add('future',-1,3)
    add('failed',5,2,status='FAILED')
    add('mismatch',5,2,fact_pub='old')
    assert Backend(db).deal_window_counts(at=at)=={'fresh_30m':20,'total_24h':266}


def test_empty_counts_and_inclusive_boundaries():
    mm=pytest.importorskip('mongomock')
    db=mm.MongoClient(tz_aware=True).counts
    at=datetime(2026,10,25,12,tzinfo=timezone.utc)
    assert Backend(db).deal_window_counts(at=at)=={'fresh_30m':0,'total_24h':0}
    for i,minutes in enumerate([30,1440]):
        db.pipeline_status.insert_one({'raw_id':i,'publication_id':'p','status':'PUBLISHED','published_at':at-timedelta(minutes=minutes)})
        db.fact_table.insert_one({'raw_id':i,'publication_id':'p','product':{}})
    assert Backend(db).deal_window_counts(at=at)=={'fresh_30m':1,'total_24h':2}
