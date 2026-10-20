"""Real HTTP + real MongoDB; mocked converter/LLM; no Telegram or external calls.
Run: python -m pytest superdeal_mongo_backend\\test_http_mongodb_e2e.py -v
"""
import json
import os
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest
from pymongo import MongoClient
from backend import Backend
from api import make_handler


@pytest.fixture
def system():
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017'), serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    name = 'superdeal_test_http_' + uuid4().hex
    backend = Backend(client[name])
    server = None
    thread = None
    try:
        backend.setup()
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(backend, admin_token='integration-secret'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        yield backend, f'http://127.0.0.1:{server.server_port}'
    finally:
        if server is not None:
            server.shutdown()
            if thread is not None:
                thread.join(timeout=5)
            server.server_close()
        client.drop_database(name)
        client.close()


def fetch(url, token=None, method='GET'):
    headers = {'Authorization': 'Bearer ' + token} if token is not None else {}
    request = Request(url, headers=headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, json.load(response)
    except HTTPError as exc:
        return exc.code, json.load(exc)


def product(url, name):
    return {'product_name': name, 'brand': 'Sony', 'ecommerce_platform': 'Amazon',
            'deal_price': 999, 'original_price': 1999, 'discount_percentage': 50,
            'affiliate_urls': [url], 'confidence': 95, 'issues': []}


def configure(backend, *items):
    text = '\n'.join(item['affiliate_urls'][0] for item in items)
    backend.converter = lambda _: {'response_text': text, 'response_payload': {'data': text, 'success': True}}
    backend.llm = lambda _: {'products': list(items), 'unassigned_urls': [],
                             'message_issues': [], 'analysis_summary': 'Controlled test'}


def test_health_real_mongodb(system):
    _, base = system
    assert fetch(base + '/health') == (200, {'status': 'ok'})


def test_real_publish_list_detail_and_pagination(system):
    backend, base = system
    u1, u2 = 'https://example.com/affiliate-a', 'https://example.com/affiliate-b'
    configure(backend, product(u1, 'Sony A'), product(u2, 'Sony B'))
    raw_id = backend.ingest('@test', '1', 'Controlled original')
    assert backend.process(raw_id) == 2
    code, page = fetch(base + '/api/v1/deals?limit=1&offset=0')
    assert code == 200 and len(page['items']) == 1 and page['has_more'] is True
    code, second = fetch(base + '/api/v1/deals?limit=1&offset=1')
    assert code == 200 and len(second['items']) == 1 and second['has_more'] is False
    assert {page['items'][0]['product_name'], second['items'][0]['product_name']} == {'Sony A', 'Sony B'}
    assert {page['items'][0]['affiliate_urls'][0], second['items'][0]['affiliate_urls'][0]} == {u1, u2}
    deal_id = second['items'][0]['id']
    assert fetch(base + '/api/v1/deals/' + deal_id)[1]['id'] == deal_id
    assert fetch(base + '/api/v1/deals/not-found')[0] == 404
    assert backend.db.ek_raw.find_one({'raw_id': raw_id})['response_payload']['success'] is True


def test_failed_second_product_never_visible_and_logs(system):
    backend, base = system
    configure(backend, product('https://example.com/ok', 'OK'), product('https://example.com/bad', 'Bad'))
    backend.llm = lambda _: {'products': [product('https://example.com/ok', 'OK'),
                                          product('https://example.com/INVENTED', 'Bad')],
                             'unassigned_urls': [], 'message_issues': [], 'analysis_summary': 'Bad'}
    raw_id = backend.ingest('@test', '2', 'Original')
    assert backend.process(raw_id) == 0
    assert backend.db.pipeline_status.find_one({'raw_id': raw_id})['status'] == 'FAILED'
    assert fetch(base + '/api/v1/deals')[1]['items'] == []
    assert backend.db.pipeline_logs.count_documents({'raw_id': raw_id, 'severity': 'ERROR'}) >= 1
    with pytest.raises(RuntimeError, match='Only PENDING'):
        backend.process(raw_id)


def test_staged_facts_are_invisible_over_http(system):
    backend, base = system
    raw_id = backend.ingest('@test', '3', 'Original')
    backend.db.fact_table.insert_one({'raw_id': raw_id, 'offer_index': 0,
                                      'publication_id': 'not-committed',
                                      'product': product('https://example.com/staged', 'Staged')})
    assert fetch(base + '/api/v1/deals')[1]['items'] == []


def test_admin_auth_and_real_audit_records(system):
    backend, base = system
    raw_id = backend.ingest('@test', '4', 'Original')
    backend.converter = lambda _: (_ for _ in ()).throw(RuntimeError('Mock conversion failed'))
    assert backend.process(raw_id) == 0
    for endpoint in ('status', 'logs'):
        url = base + '/api/v1/admin/' + endpoint
        assert fetch(url)[0] == 401
        assert fetch(url, token='wrong')[0] == 401
        code, body = fetch(url, token='integration-secret')
        assert code == 200 and body['items']
    status = fetch(base + '/api/v1/admin/status', token='integration-secret')[1]['items']
    logs = fetch(base + '/api/v1/admin/logs', token='integration-secret')[1]['items']
    assert any(s['status'] == 'FAILED' for s in status)
    assert any(log['event'] == 'STAGE_FAILED' for log in logs)


def test_validation_and_read_only_http(system):
    _, base = system
    assert fetch(base + '/api/v1/deals?limit=-1')[0] == 400
    assert fetch(base + '/api/v1/deals?offset=10001')[0] == 400
    assert fetch(base + '/api/v1/deals', method='POST')[0] == 405
