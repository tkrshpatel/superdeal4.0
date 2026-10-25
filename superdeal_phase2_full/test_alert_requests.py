from datetime import datetime, timezone, timedelta
import mongomock
from alert_requests import list_requests

def test_inspection_is_read_only_and_never_exposes_private_tokens():
    db=mongomock.MongoClient().db
    at=datetime.now(timezone.utc)
    db.deal_alerts.insert_one({'product':'Headphones','email':'owner@example.com','daily_limit':2,'days':7,
        'status':'pending','created_at':at,'expires_at':at+timedelta(days=1),
        'stop_token':'SECRET_STOP','stop_hash':'SECRET_HASH','confirm_hash':'SECRET_CONFIRM','arbitrary':'PRIVATE'})
    before=list(db.deal_alerts.find({}))
    rows=list_requests(db,email=' OWNER@example.com ',at=at)
    assert len(rows)==1
    assert rows[0]['product']=='Headphones'
    assert rows[0]['email']=='o***@example.com'
    assert 'SECRET' not in str(rows)
    assert 'arbitrary' not in rows[0]
    assert list(db.deal_alerts.find({}))==before

def test_inspection_reports_expiry_without_writing():
    db=mongomock.MongoClient().db
    at=datetime.now(timezone.utc)
    db.deal_alerts.insert_one({'product':'Shoes','email':'owner@example.com','status':'active','created_at':at,'expires_at':at-timedelta(seconds=1)})
    assert list_requests(db,at=at)[0]['status']=='expired'
    assert db.deal_alerts.find_one({})['status']=='active'
