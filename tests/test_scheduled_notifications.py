from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import mongomock
import pytest
from notifications import NotificationRequests
from notification_worker import NotificationWorker, matches_request, candidates, LOOKBACK

AT = datetime(2026, 10, 27, 6, tzinfo=timezone.utc)


class Mail:
    origin = 'https://thesuperdeals.in'
    def __init__(self, fail=False):
        self.messages = []
        self.fail = fail
    def send(self, *args):
        self.messages.append(args)
        if self.fail:
            raise TimeoutError('recipient/password must not be logged')
        return 'sent'


def fixture(cap=2, fail=False):
    db = mongomock.MongoClient(tz_aware=True).db
    NotificationRequests(db).save({'product':'iPhone 17 Pro', 'email':'buyer@example.com',
        'daily_limit':cap, 'days':2, 'consent':True}, at=AT-timedelta(hours=1))
    mail = Mail(fail)
    worker = NotificationWorker(db, mail)
    worker.setup()
    return db, mail, worker


def deals(*ids):
    return [{'id':i, 'product_name':'Apple iPhone 17 Pro', 'deal_price':90000} for i in ids]


@pytest.mark.parametrize('query,title,expected', [
    ('headphones','Sony Headphones',True), ('headphones','Sony Earbuds',False),
    ('iPhone 17 Pro','iPhone 17',True), ('iPhone 17 Pro','iPhone case',False),
    ('Sony Sony','Sony speaker',True), ('','Any product',False),
    ('IPHONE17','iPhone 17',True), ('Puma shoes','Pumax shoeshine',False)])
def test_exact_word_threshold(query,title,expected):
    assert matches_request(query,title) is expected


def test_digest_duplicate_and_restart_schedule():
    db, mail, worker = fixture()
    assert worker.run_once(None,at=AT,deals=deals('a','b'))['sent'] == 1
    assert len(mail.messages) == 1 and '/go/a' in mail.messages[0][2] and '/go/b' in mail.messages[0][2]
    assert worker.run_once(None,at=AT+timedelta(hours=1),deals=deals('c'))['not_due']
    assert NotificationWorker(db,mail).run_once(None,at=AT+timedelta(hours=12),deals=deals('a','b'))['sent'] == 0
    assert db.notification_deliveries.count_documents({'state':'sent'}) == 2


def test_daily_limit_ist_and_release_unsent_reservations():
    db, mail, worker = fixture(cap=1)
    worker.run_once(None,at=AT,deals=deals('a'))
    stats=worker.run_once(None,at=AT+timedelta(hours=12),deals=deals('b'))
    assert stats['skipped'] == 1 and len(mail.messages) == 1
    assert db.notification_deliveries.count_documents({'deal_id':'b'}) == 0
    worker.run_once(None,at=AT+timedelta(hours=24),deals=deals('b'))
    assert len(mail.messages) == 2


def test_failed_smtp_never_resends_unknown_outcome():
    db, mail, worker=fixture(fail=True)
    assert worker.run_once(None,at=AT,deals=deals('a'))['failed'] == 1
    row=db.notification_deliveries.find_one({})
    assert row['state']=='failed_or_unknown' and row['error_type']=='TimeoutError'
    assert 'password' not in str(row)
    worker.run_once(None,at=AT+timedelta(hours=12),deals=deals('a'))
    assert len(mail.messages)==1


@pytest.mark.parametrize('patch', [{'status':'stopped'},{'consent':False},{'expires_at':AT}])
def test_inactive_or_expired_never_sends(patch):
    db, mail, worker=fixture()
    db.notification_table.update_one({}, {'$set':patch})
    worker.run_once(None,at=AT,deals=deals('a'))
    assert not mail.messages


def test_legacy_saved_request_derives_expiry_from_ds():
    db, mail, worker=fixture()
    db.notification_table.update_one({}, {'$unset':{'expires_at':''}})
    worker.run_once(None,at=AT+timedelta(days=3),deals=deals('a'))
    assert not mail.messages and db.notification_table.find_one({})['status']=='expired'


def test_pre_send_cancellation_rechecked():
    db,mail,worker=fixture()
    insert=db.notification_deliveries.insert_one
    def cancel(doc):
        result=insert(doc)
        db.notification_table.update_one({}, {'$set':{'status':'stopped'}})
        return result
    db.notification_deliveries.insert_one=cancel
    worker.run_once(None,at=AT,deals=deals('a'))
    assert not mail.messages


def test_candidate_query_exact_window_committed_gate_and_no_limit():
    seen=[]
    class Facts:
        def aggregate(self,pipeline):
            seen.extend(pipeline)
            return []
    backend=SimpleNamespace(db=SimpleNamespace(fact_table=Facts()),
        _published_pipeline=lambda limit:[{'$match':{'committed':True}},{'$limit':limit},{'$project':{'product':1}}])
    assert list(candidates(backend, AT))==[]
    assert not any('$limit' in s for s in seen)
    assert seen[-2]['$match']['_publication.published_at']=={'$gte':AT-LOOKBACK,'$lte':AT}
    assert LOOKBACK==timedelta(hours=11,minutes=59)


def test_notification_service_uses_worker_credentials_and_detects_duplicates():
    import importlib.util
    from pathlib import Path
    path=Path(__file__).resolve().parents[1]/'scripts'/'start_pipeline.py'
    spec=importlib.util.spec_from_file_location('notification_launcher_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    env=module.service_environment('notifications',{'MONGODB_URI':'mongodb://x','TELEGRAM_API_HASH':'secret'},'workerpass')
    assert env[module.SECRET]=='workerpass' and 'TELEGRAM_API_HASH' not in env
    assert module.process_matches('notifications', {'Name':'python.exe','CommandLine':f'python "{module.ROOT}/scripts/start_pipeline.py" --service notifications'})


def test_intake_marks_active_only_when_explicitly_enabled(monkeypatch):
    monkeypatch.setenv('SUPERDEAL_NOTIFICATIONS_ENABLED','1')
    db, _, _ = fixture()
    row = db.notification_table.find_one({})
    assert row['status']=='active' and row['delivery_enabled'] is True
    assert row['expires_at']==row['ds']+timedelta(days=2)
