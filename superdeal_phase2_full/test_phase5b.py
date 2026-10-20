"""Phase 5b: live MongoDB search and exact affiliate redirects, synthetic data only."""
import os
import threading
from uuid import uuid4
from urllib.request import build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from pymongo import MongoClient
from backend import Backend
from api import make_handler

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None

def test_search_and_affiliate_redirect():
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/?replicaSet=rs0'), serverSelectionTimeoutMS=5000)
    name = 'superdeal_test_phase5b_' + uuid4().hex
    b = Backend(client[name]); server = None
    try:
        b.setup()
        for i, (name_, merchant, price) in enumerate([('Sony Headphones', 'Amazon', 1999), ('boAt Speaker', 'Flipkart', 999), ('Sony TV', 'Amazon', 49999)]):
            url = 'https://example.com/offer?ref=ab%2Fcd&n=' + str(i)
            b.converter = lambda _, u=url: {'response_text': u, 'response_payload': {'data': u}}
            b.llm = lambda _, n=name_, m=merchant, p=price, u=url: {'products': [{'product_name': n, 'brand': None, 'ecommerce_platform': m, 'deal_price': p, 'original_price': None, 'discount_percentage': None, 'affiliate_urls': [u], 'confidence': 90, 'issues': []}], 'unassigned_urls': [], 'message_issues': [], 'analysis_summary': ''}
            assert b.process(b.ingest('@phase5b', str(i), 'synthetic')) == 1
        assert len(b.legacy_search(q='sony')['items']) == 2
        assert len(b.legacy_search(merchant='amazon')['items']) == 2
        assert len(b.legacy_search(min_price=1000, max_price=5000)['items']) == 1
        assert [x['deal_price'] for x in b.legacy_search(sort='price_asc')['items']] == [999,1999,49999]
        assert [x['deal_price'] for x in b.legacy_search(sort='price_desc')['items']] == [49999,1999,999]
        assert len(b.legacy_search(q='sony', merchant='amazon', max_price=2000)['items']) == 1
        assert not b.legacy_search(q='nonexistent')['items']
        server = ThreadingHTTPServer(('127.0.0.1',0), make_handler(b, admin_token='test-token'))
        thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        import json
        from urllib.request import urlopen
        with urlopen(base+'/deals?q=Sony&sort=price_asc') as r: payload = json.load(r)
        assert [x['current_price'] for x in payload['deals']] == [1999,49999]
        item = payload['deals'][0]
        opener = build_opener(NoRedirect())
        try: opener.open(base+'/go/'+item['id'])
        except HTTPError as exc:
            assert exc.code == 302
            assert exc.headers['Location'] == 'https://example.com/offer?ref=ab%2Fcd&n=0'
        else: raise AssertionError('Expected HTTP redirect')
        assert b.db.deal_clicks.count_documents({'deal_id': item['id']}) == 1
        assert b.affiliate_destination('bad-id') is None
        assert len(b.legacy_search(q='.*')['items']) == 0
    finally:
        if server: server.shutdown(); thread.join(timeout=3); server.server_close()
        client.drop_database(name); client.close()
