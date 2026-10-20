import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from api import make_handler


class Cursor:
    def __init__(self, docs): self.docs = docs
    def sort(self, *args): return self
    def limit(self, n): return self.docs[:n]


class Collection:
    def __init__(self, docs): self.docs = docs
    def find(self, *_): return Cursor(self.docs)


class DB:
    pipeline_status = Collection([{'_id': 1, 'raw_id': 2, 'status': 'FAILED'}])
    pipeline_logs = Collection([{'_id': 3, 'raw_id': 2, 'event': 'STAGE_FAILED'}])
    def command(self, name): assert name == 'ping'


class BackendStub:
    db = DB()
    def published_offers(self, limit=100):
        return [{'id': 'p1', 'product_name': 'Sony', 'affiliate_urls': ['https://fktr.in/abc']},
                {'id': 'p2', 'product_name': 'Samsung', 'affiliate_urls': ['https://fktr.in/def']}][:limit]


@pytest.fixture
def server():
    http = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(BackendStub(), admin_token='test-secret'))
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    yield f'http://127.0.0.1:{http.server_port}'
    http.shutdown()
    thread.join(timeout=3)
    http.server_close()


def fetch(url, *, token=None, method='GET'):
    headers = {'Authorization': f'Bearer {token}'} if token else {}
    req = Request(url, headers=headers, method=method)
    try:
        with urlopen(req, timeout=3) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


def test_health(server):
    assert fetch(server + '/health') == (200, {'status': 'ok'})


def test_pagination(server):
    code, body = fetch(server + '/api/v1/deals?limit=1&offset=1')
    assert code == 200 and [x['id'] for x in body['items']] == ['p2']
    assert not body['has_more']


def test_deal_detail(server):
    assert fetch(server + '/api/v1/deals/p1')[1]['affiliate_urls'] == ['https://fktr.in/abc']
    assert fetch(server + '/api/v1/deals/missing')[0] == 404


def test_admin_requires_token(server):
    assert fetch(server + '/api/v1/admin/status')[0] == 401
    assert fetch(server + '/api/v1/admin/status', token='wrong')[0] == 401
    code, data = fetch(server + '/api/v1/admin/status', token='test-secret')
    assert code == 200 and data['items'][0]['status'] == 'FAILED'
    assert fetch(server + '/api/v1/admin/logs', token='test-secret')[1]['items'][0]['event'] == 'STAGE_FAILED'


def test_invalid_and_read_only(server):
    assert fetch(server + '/api/v1/deals?limit=-1')[0] == 400
    assert fetch(server + '/api/v1/deals?limit=101')[0] == 400
    assert fetch(server + '/api/v1/deals', method='POST')[0] == 405
