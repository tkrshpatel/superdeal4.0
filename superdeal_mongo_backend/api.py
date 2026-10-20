"""Opt-in read-only HTTP API. Does not start Telegram or background processing."""
from __future__ import annotations

import hmac
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from backend import connect


def _integer(values, key, default, maximum):
    value = values.get(key, [str(default)])
    if len(value) != 1 or not value[0].isdigit():
        raise ValueError(f'{key} must be a nonnegative integer')
    number = int(value[0])
    if number > maximum:
        raise ValueError(f'{key} must be <= {maximum}')
    return number


def make_handler(backend, *, admin_token=None):
    """Inject backend for isolated tests; no connection created on import."""
    token = admin_token if admin_token is not None else os.getenv('SUPERDEAL_ADMIN_TOKEN', '')

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, payload):
            data = json.dumps(payload, default=str, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlsplit(self.path)
            try:
                params = parse_qs(url.query, keep_blank_values=True)
                if url.path == '/health':
                    backend.db.command('ping')
                    return self._send(200, {'status': 'ok'})
                if url.path == '/api/v1/deals':
                    limit = _integer(params, 'limit', 20, 100)
                    offset = _integer(params, 'offset', 0, 10000)
                    # Fetch one extra to detect another page; never return raw/failed deals.
                    batch = backend.published_offers(limit=max(1, offset + limit + 1))
                    items = batch[offset:offset + limit]
                    return self._send(200, {'items': items, 'limit': limit, 'offset': offset,
                                            'has_more': len(batch) > offset + limit})
                if url.path.startswith('/api/v1/deals/'):
                    deal_id = url.path[len('/api/v1/deals/'):]
                    if not deal_id or '/' in deal_id:
                        return self._send(404, {'error': 'not_found'})
                    # Use publication-gated accessor, not direct fact_table queries.
                    item = next((p for p in backend.published_offers(limit=10001) if p['id'] == deal_id), None)
                    return self._send(200, item) if item else self._send(404, {'error': 'not_found'})
                if url.path in ('/api/v1/admin/status', '/api/v1/admin/logs'):
                    supplied = self.headers.get('Authorization', '')
                    if not token or not hmac.compare_digest(supplied, 'Bearer ' + token):
                        return self._send(401, {'error': 'unauthorized'})
                    limit = _integer(params, 'limit', 20, 100)
                    collection = backend.db.pipeline_status if url.path.endswith('status') else backend.db.pipeline_logs
                    order = 'updated_at' if url.path.endswith('status') else 'timestamp'
                    docs = list(collection.find({}).sort(order, -1).limit(limit))
                    # Never expose Mongo ObjectId serialization internals.
                    for doc in docs:
                        doc['_id'] = str(doc['_id'])
                        if 'raw_id' in doc:
                            doc['raw_id'] = str(doc['raw_id'])
                    return self._send(200, {'items': docs})
                return self._send(404, {'error': 'not_found'})
            except ValueError as exc:
                return self._send(400, {'error': 'bad_request', 'detail': str(exc)})
            except Exception:
                # Do not leak stack traces or secrets in HTTP responses.
                import logging
                logging.getLogger('superdeal.api').exception('HTTP API request failed')
                return self._send(500, {'error': 'internal_error'})

        def do_POST(self):
            self._send(405, {'error': 'method_not_allowed'})

    return Handler


def main():
    host = os.getenv('SUPERDEAL_API_HOST', '127.0.0.1')
    port = int(os.getenv('SUPERDEAL_API_PORT', '8765'))
    backend = connect()
    backend.setup()
    server = ThreadingHTTPServer((host, port), make_handler(backend))
    print(f'SuperDeal isolated read-only API: http://{host}:{port}')
    server.serve_forever()


if __name__ == '__main__':
    main()
