"""No external SMTP or production database is used by these tests."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import mongomock
import pytest
from notifications import Alerts, Mailer, matches, validate_request

@pytest.fixture(autouse=True)
def enable_dispatch_in_isolated_tests(monkeypatch):
    # Tests use mongomock and a fake mailer, never real SMTP.
    monkeypatch.setenv('SUPERDEAL_ALERT_DISPATCH_ENABLED', '1')


def test_dispatch_disabled_by_default(monkeypatch):
    monkeypatch.delenv('SUPERDEAL_ALERT_DISPATCH_ENABLED', raising=False)
    instance = service()
    instance.subscribe(REQUEST, at=AT)
    assert instance.run_once(Deals([{'id': '1', 'product_name': 'iPhone 17 Pro'}]), at=AT) == {
        'confirmations': 0, 'batches': 0, 'failed': 0
    }
    assert instance.db.alert_confirmations.find_one({})['state'] == 'queued'
    assert instance.mailer.messages == []


AT = datetime(2026, 10, 25, 6, tzinfo=timezone.utc)
REQUEST = {'product': 'iPhone 17 Pro', 'email': 'buyer@example.com', 'daily_limit': 2, 'days': 7, 'consent': True}


class Preview:
    origin = 'https://superdeals.example'
    mode = 'dry-run'
    def __init__(self): self.messages = []
    def send(self, *message):
        self.messages.append(message)
        return 'previewed'


class Deals:
    def __init__(self, items): self.items = items
    def notification_candidates(self, **kwargs): return iter(self.items)


def service():
    instance = Alerts(mongomock.MongoClient(tz_aware=True).db, Preview())
    instance.setup()
    return instance


def activate(instance, request=None):
    instance.subscribe(request or REQUEST, at=AT)
    queued = instance.db.alert_confirmations.find_one({})
    assert instance.confirm(queued['confirm_token'], at=AT)
    return instance.db.deal_alerts.find_one({})


@pytest.mark.parametrize('query,title,expected', [
    ('Nike', 'Nike Running Shoes', True),
    ('Nike', 'Adidas Running Shoes', False),
    ('Nike Shoes', 'Nike Gym Shoes', True),
    ('Nike Shoes', 'Adidas Sports Shoes', False),
    ('Nike Running Shoes', 'Nike Training Shoes', True),
    ('Samsung Galaxy S24', 'Samsung Galaxy S25', True),
    ('iPhone', 'iPhone 17 Pro', True),
    ('iPhone 17 Pro', 'iPhone 16 Pro', True),
    ('iPhone 17 Pro', 'iPhone 17 Pro Max', True),
    ('iPhone 17 Pro', 'iPhone 17', True),
    ('iPhone 17 Pro', 'Case for iPhone 17 Pro', True),
    ('iPhone 17 Pro', 'Apple MacBook Air', False),
    ('Nike Nike Shoes', 'Nike gym bag', False),
    ('Nike Nike Shoes', 'Nike shoes', True),
    ('NIKE shoes', 'nike Training SHOES', True),
    ('Pro', 'Productivity Suite', False),
    ('', 'Nike Shoes', False),
    ('Nike', '', False),
])
def test_notification_word_threshold(query, title, expected):
    assert matches(query, title) is expected


@pytest.mark.parametrize('patch', [{'consent': False}, {'daily_limit': True}, {'days': 31}, {'email': 'x\r\nBcc: x@y.com'}, {'product': '<img src=x>'}, {'product': '---'}, {'days': '7'}, {'daily_limit': 100}, {'extra': 'ignored?'}])
def test_validate_rejects_bad_input(patch):
    with pytest.raises(ValueError): validate_request({**REQUEST, **patch})


def test_pending_confirmation_dedupe_and_expiry():
    instance = service()
    instance.subscribe(REQUEST, at=AT)
    instance.subscribe({**REQUEST, 'daily_limit': 5}, at=AT)
    assert instance.db.deal_alerts.count_documents({}) == 1
    assert instance.db.alert_confirmations.count_documents({}) == 1
    assert instance.run_once(Deals([]), at=AT)['confirmations'] == 1
    assert len(instance.mailer.messages) == 1
    assert instance.db.deal_alerts.find_one({})['status'] == 'pending'
    assert instance.run_once(Deals([]), at=AT)['confirmations'] == 0
    assert instance.db.deal_alerts.find_one({})['daily_limit'] == 2
    instance.run_once(Deals([]), at=AT + timedelta(days=2))
    assert instance.db.deal_alerts.find_one({})['status'] == 'expired'


def test_only_verified_new_deals_and_unsubscribe():
    instance = service()
    instance.subscribe(REQUEST, at=AT)
    queued = instance.db.alert_confirmations.find_one({})
    candidate = {'id': 'abc', 'product_name': 'iPhone 17 Pro 256GB', 'deal_price': 99999}
    assert instance.run_once(Deals([candidate]), at=AT)['batches'] == 0
    assert instance.confirm(queued['confirm_token'], at=AT)
    assert not instance.confirm(queued['confirm_token'], at=AT)
    assert instance.run_once(Deals([candidate]), at=AT)['batches'] == 1
    assert '/go/abc' in instance.mailer.messages[-1][2]
    assert 'INR 99999' in instance.mailer.messages[-1][2]
    assert instance.run_once(Deals([candidate]), at=AT + timedelta(hours=13))['batches'] == 0
    alert = instance.db.deal_alerts.find_one({})
    assert instance.stop(alert['stop_token'])
    assert instance.run_once(Deals([{**candidate, 'id': 'next'}]), at=AT + timedelta(days=1))['batches'] == 0


def test_daily_cap_spacing_reset_and_expiration():
    instance = service()
    activate(instance, {**REQUEST, 'daily_limit': 1, 'days': 2})
    one = lambda name: Deals([{'id': name, 'product_name': 'iPhone 17 Pro', 'deal_price': None}])
    assert instance.run_once(one('1'), at=AT)['batches'] == 1
    assert instance.run_once(one('2'), at=AT + timedelta(hours=10))['batches'] == 0
    assert instance.run_once(one('2'), at=AT + timedelta(days=1))['batches'] == 1
    assert instance.run_once(one('3'), at=AT + timedelta(days=2))['batches'] == 0
    assert instance.db.deal_alerts.find_one({})['status'] == 'expired'
    assert 'View price at retailer' in instance.mailer.messages[-1][2]


def test_parallel_workers_do_not_duplicate_or_exceed_cap():
    instance = service()
    activate(instance)
    deals = Deals([{'id': '1', 'product_name': 'iPhone 17 Pro'}])
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: instance.run_once(deals, at=AT), range(4)))
    assert sum(r['batches'] for r in results) == 1
    assert instance.db.alert_deliveries.count_documents({}) == 1
    assert instance.db.deal_alerts.find_one({})['daily_count'] == 1


def test_uncertain_send_is_not_automatically_retried():
    instance = service()
    activate(instance)
    def fail(*_): raise TimeoutError('SMTP outcome unknown')
    instance.mailer.send = fail
    deals = Deals([{'id': '1', 'product_name': 'iPhone 17 Pro'}])
    assert instance.run_once(deals, at=AT)['failed'] == 1
    assert instance.run_once(deals, at=AT + timedelta(days=1))['batches'] == 0
    assert instance.db.alert_deliveries.find_one({})['state'] == 'reserved'


def test_dry_run_creates_private_preview_without_smtp(tmp_path, monkeypatch):
    monkeypatch.setenv('SUPERDEAL_EMAIL_MODE', 'dry-run')
    monkeypatch.setenv('SUPERDEAL_EMAIL_PREVIEW_DIR', str(tmp_path))
    assert Mailer().send('x@example.com', 'Preview', 'Hello') == 'previewed'
    assert len(list(tmp_path.glob('*.eml'))) == 1
    assert 'Hello' in next(tmp_path.glob('*.eml')).read_text()


def test_email_confirmation_expires_and_rejects_invalid_tokens():
    instance = service()
    instance.subscribe(REQUEST, at=AT)
    token = instance.db.alert_confirmations.find_one({})['confirm_token']
    assert not instance.confirm(token, at=AT + timedelta(days=1))
    with pytest.raises(ValueError): instance.confirm('bad')


def test_http_submission_private_and_origin_body_limits(monkeypatch):
    from api import make_handler
    monkeypatch.setenv('SUPERDEAL_EMAIL_MODE', 'dry-run')
    db = mongomock.MongoClient(tz_aware=True).db
    backend = type('Backend', (), {'db': db})()
    http = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(backend))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{http.server_port}'
    def post(path, body, origin=None):
        request = Request(base + path, data=body, headers={'Content-Type': 'application/json', **({'Origin': origin} if origin else {})})
        try:
            with urlopen(request) as response: return response.code, json.load(response)
        except HTTPError as error: return error.code, json.load(error)
    try:
        status, payload = post('/api/v1/alerts', json.dumps(REQUEST).encode(), base)
        assert status == 202
        assert REQUEST['email'] not in json.dumps(payload)
        assert 'token' not in json.dumps(payload)
        assert post('/api/v1/alerts', json.dumps(REQUEST).encode(), 'https://evil.example')[0] == 403
        assert post('/api/v1/alerts', b'x' * 4097)[0] == 413
        assert post('/api/v1/alerts', b'{}')[0] == 400
        assert post('/api/v1/alerts', b'not json')[0] == 400
        token = db.alert_confirmations.find_one({})['confirm_token']
        assert post('/api/v1/alerts/confirm', json.dumps({'token': token}).encode())[0] == 200
        assert db.deal_alerts.find_one({})['status'] == 'active'
        # There is deliberately no endpoint to list subscribers or their email addresses.
        with pytest.raises(HTTPError) as denied: urlopen(base + '/api/v1/alerts')
        assert denied.value.code == 404
    finally:
        http.shutdown(); thread.join(timeout=3); http.server_close()


def test_repeat_signup_with_default_naive_mongo_dates():
    instance = Alerts(mongomock.MongoClient().db, Preview())
    instance.setup()
    instance.subscribe(REQUEST, at=AT)
    instance.subscribe(REQUEST, at=AT)
    assert instance.db.deal_alerts.count_documents({}) == 1


def test_candidate_query_keeps_publication_gate_and_has_no_card_limit():
    from backend import Backend
    class Collection:
        def aggregate(self, pipeline):
            assert any('$lookup' in stage for stage in pipeline)
            assert any(stage.get('$match', {}).get('_publication.status') == 'PUBLISHED' for stage in pipeline)
            assert any('_publication.published_at' in stage.get('$match', {}) for stage in pipeline)
            assert not any('$limit' in stage for stage in pipeline)
            return [{'_id':'abc','product':{'product_name':'iPhone 17 Pro','deal_price':999}}]
    backend = Backend(type('DB', (), {'fact_table':Collection()})())
    assert list(backend.notification_candidates(at=AT))[0]['deal_price'] == 999


def test_smtp_cannot_use_placeholder_sender(monkeypatch):
    monkeypatch.setenv('SUPERDEAL_EMAIL_MODE','smtp')
    monkeypatch.setenv('SUPERDEAL_PUBLIC_URL','https://superdeals.example')
    monkeypatch.setenv('SUPERDEAL_EMAIL_FROM','SuperDeals <alerts@superdeals.invalid>')
    with pytest.raises(ValueError): Mailer()

@pytest.mark.parametrize('name', ['Headphones', 'Shoes', 'iPhone', 'PS5'])
def test_single_word_products_are_valid(name):
    assert validate_request({**REQUEST, 'product': name})[0] == name

def test_broad_product_matches_headphones_deal():
    assert matches('Headphones', 'Sony Wireless Headphones')


def test_notification_window_is_11_hours_59_minutes():
    from backend import Backend
    captured = []
    class Collection:
        def aggregate(self, pipeline):
            captured.append(pipeline)
            return []
    backend = Backend(type('DB', (), {'fact_table': Collection()})())
    assert list(backend.notification_candidates(at=AT, window=timedelta(hours=11, minutes=59))) == []
    match = next(stage['$match']['_publication.published_at']
                 for stage in captured[0]
                 if '_publication.published_at' in stage.get('$match', {}))
    assert match == {'$gte': AT - timedelta(hours=11, minutes=59), '$lte': AT}
