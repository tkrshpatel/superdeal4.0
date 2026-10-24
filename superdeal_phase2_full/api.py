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


def _legacy_deal(product, metadata=None):
    """Read-only field adapter; unknown values remain null, not fabricated."""
    urls = product.get('affiliate_urls') or []
    metadata = metadata or {}
    return {
        'id': product['id'],  # Mongo ObjectId string; callers must not cast to int.
        'product_name': product.get('product_name'),
        'brand': product.get('brand'),
        'merchant': product.get('ecommerce_platform'),
        'current_price': product.get('deal_price'),
        'mrp': product.get('original_price'),
        'discount_pct': product.get('discount_percentage'),
        'affiliate_url': urls[0] if urls else None,
        'affiliate_urls': urls,
        'image_url': product.get('image_url'),
        'deal_terms': product.get('deal_terms'),
        'click_count': metadata.get('click_count'),
        'hot': metadata.get('hot'),
        'last_seen_at': metadata.get('published_at'),
        'fresh': metadata.get('fresh'),
        'enrichment_status': product.get('enrichment_status'),
    }


def make_handler(backend, *, admin_token=None):
    """Inject backend for isolated tests; no connection created on import."""
    token = admin_token if admin_token is not None else os.getenv('SUPERDEAL_ADMIN_TOKEN', '')

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, payload):
            # Authenticated admin diagnostics retain provenance; shopper routes do not.
            if not self.path.startswith('/api/v1/admin/'):
                from public_presentation import public_payload
                payload = public_payload(payload)
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
                # Read-only legacy web contract. This adapter does not invent click counts,
                # freshness, price verification, or historical observations.
                if url.path == '/deals':
                    limit = _integer(params, 'limit', 50, 100)
                    q = params.get('q', [None])[0]
                    merchant = params.get('merchant', [None])[0]
                    min_price = _integer(params, 'min_price', 0, 1000000000) if 'min_price' in params else None
                    max_price = _integer(params, 'max_price', 0, 1000000000) if 'max_price' in params else None
                    sort = params.get('sort', ['newest'])
                    if len(sort) != 1: raise ValueError('sort must be specified once')
                    if hasattr(backend, 'legacy_search'):
                        page = backend.legacy_search(limit=limit, q=q, merchant=merchant,
                                                     min_price=min_price, max_price=max_price, sort=sort[0])
                    else:
                        # Existing lightweight test stubs do not implement searching.
                        if set(params) & {'q', 'merchant', 'min_price', 'max_price', 'sort'}:
                            return self._send(400, {'error': 'unsupported_legacy_filters'})
                        page = backend.published_page(limit=limit, offset=0)
                    return self._send(200, {'deals': [_legacy_deal(x, backend.public_metadata(x['id']) if hasattr(backend, 'public_metadata') else None) for x in page['items']],
                                            'counts': backend.deal_window_counts() if hasattr(backend, 'deal_window_counts') else None,
                                            'fresh_window_hours': 24 if hasattr(backend, 'public_metadata') else None, 'has_more': page['has_more']})
                if url.path.startswith('/deals/') and url.path.endswith('/price-history'):
                    return self._send(501, {'error': 'price_history_not_implemented', 'detail': 'No independent price observations have been collected'})
                if url.path.startswith('/deals/'):
                    suffix = url.path[len('/deals/'):]
                    if not suffix or '/' in suffix:
                        return self._send(404, {'error': 'not_found'})
                    item = backend.published_offer_by_id(suffix)
                    return self._send(200, _legacy_deal(item, backend.public_metadata(item['id']) if hasattr(backend, 'public_metadata') else None)) if item else self._send(404, {'error': 'not_found'})
                if url.path.startswith('/go/'):
                    deal_id = url.path[len('/go/'):]
                    if not deal_id or '/' in deal_id:
                        return self._send(404, {'error': 'not_found'})
                    if not hasattr(backend, 'affiliate_destination'):
                        return self._send(404, {'error': 'not_found'})
                    destination = backend.affiliate_destination(deal_id)
                    if destination is None:
                        return self._send(404, {'error': 'not_found'})
                    backend.record_affiliate_click(deal_id)
                    self.send_response(302)
                    self.send_header('Location', destination)
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                if url.path == '/api/v1/deals':
                    limit = _integer(params, 'limit', 20, 100)
                    offset = _integer(params, 'offset', 0, 10000)
                    if hasattr(backend, 'published_page'):
                        return self._send(200, backend.published_page(limit=limit, offset=offset))
                    # Compatibility with lightweight stub used by older unit tests.
                    batch = backend.published_offers(limit=max(1, offset + limit + 1))
                    return self._send(200, {'items': batch[offset:offset + limit],
                                            'limit': limit, 'offset': offset,
                                            'has_more': len(batch) > offset + limit})
                if url.path.startswith('/api/v1/deals/'):
                    deal_id = url.path[len('/api/v1/deals/'):]
                    if not deal_id or '/' in deal_id:
                        return self._send(404, {'error': 'not_found'})
                    # Indexed _id lookup with committed-publication gate.
                    item = (backend.published_offer_by_id(deal_id) if hasattr(backend, 'published_offer_by_id')
                            else next((p for p in backend.published_offers(limit=10001) if p['id'] == deal_id), None))
                    return self._send(200, item) if item else self._send(404, {'error': 'not_found'})
                if url.path in ('/api/v1/admin/status', '/api/v1/admin/logs'):
                    supplied = self.headers.get('Authorization', '')
                    if not token or not hmac.compare_digest(supplied, 'Bearer ' + token):
                        return self._send(401, {'error': 'unauthorized'})
                    limit = _integer(params, 'limit', 20, 100)
                    collection = backend.db.pipeline_status if url.path.endswith('status') else backend.db.pipeline_logs
                    order = 'updated_at' if url.path.endswith('status') else 'timestamp'
                    docs = list(collection.find({}).sort(order, -1).limit(limit))
                    # Admin responses must not expose exception text, raw data,
                    # tracebacks, tokens, or arbitrary provider payloads.
                    safe_keys = ({'_id', 'raw_id', 'status', 'current_stage',
                                  'products_extracted', 'products_published',
                                  'created_at', 'updated_at', 'published_at'}
                                 if url.path.endswith('status') else
                                 {'_id', 'raw_id', 'stage', 'severity', 'event', 'timestamp'})
                    docs = [{k: (str(v) if k in ('_id', 'raw_id') else v)
                             for k, v in doc.items() if k in safe_keys} for doc in docs]
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
    if host not in ('127.0.0.1', 'localhost', '::1') and not os.getenv('SUPERDEAL_ALLOW_REMOTE_HTTP') == '1':
        raise RuntimeError('Remote HTTP bind requires explicit SUPERDEAL_ALLOW_REMOTE_HTTP=1 and TLS reverse proxy')
    if not os.getenv('SUPERDEAL_ADMIN_TOKEN', '').strip():
        raise RuntimeError('SUPERDEAL_ADMIN_TOKEN must be configured before API startup')
    backend = connect()
    backend.setup()
    server = ThreadingHTTPServer((host, port), make_handler(backend))
    print(f'SuperDeal isolated read-only API: http://{host}:{port}')
    server.serve_forever()


if __name__ == '__main__':
    main()
