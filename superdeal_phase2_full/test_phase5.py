"""Phase 5: read-only legacy contract tests. No Telegram or live services."""
import json
import threading
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from urllib.error import HTTPError
from api import make_handler

class DB:
    def command(self, cmd):
        assert cmd == 'ping'

class Backend:
    db = DB()
    def published_page(self, *, limit, offset):
        items = [{'id': '507f1f77bcf86cd799439011', 'product_name': 'Sony headphones',
                  'ecommerce_platform': 'Amazon', 'deal_price': 1999,
                  'affiliate_urls': ['https://example.com/a?ref=abc%2F123']}]
        return {'items': items[offset:offset+limit], 'has_more': len(items) > offset+limit,
                'limit': limit, 'offset': offset}
    def published_offer_by_id(self, deal_id):
        return self.published_page(limit=1, offset=0)['items'][0] if deal_id == '507f1f77bcf86cd799439011' else None

def request(base, path):
    try:
        with urlopen(base+path, timeout=3) as r: return r.status, json.load(r)
    except HTTPError as e: return e.code, json.load(e)

def test_legacy_read_only_adapter():
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(Backend(), admin_token='secret'))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    try:
        code, data = request(base, '/deals?limit=10')
        assert code == 200 and len(data['deals']) == 1
        d = data['deals'][0]
        assert d['current_price'] == 1999 and d['merchant'] == 'Amazon'
        assert d['affiliate_url'] == 'https://example.com/a?ref=abc%2F123'
        assert d['click_count'] is None and data['fresh_window_hours'] is None
        assert request(base, '/deals/'+d['id'])[1] == d
        assert request(base, '/deals/notfound')[0] == 404
        assert request(base, '/deals?sort=popular')[0] == 400
        assert request(base, '/deals?q=sony')[0] == 400
        assert request(base, '/deals?limit=101')[0] == 400
        assert request(base, '/api/v1/deals')[0] == 200
    finally:
        server.shutdown(); thread.join(timeout=3); server.server_close()
