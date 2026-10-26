"""Public deals and opt-in alert API. No automatic workers or email sending."""
from __future__ import annotations

import hmac
import json
import os
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

from backend import connect
from http_security import safe_destination, RequestBudget, client_identity, BoundedHTTPServer


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
        'offer_facts': product.get('offer_facts'),
        'click_count': metadata.get('click_count'),
        'hot': metadata.get('hot'),
        'last_seen_at': metadata.get('published_at'),
        'fresh': metadata.get('fresh'),
        'enrichment_status': product.get('enrichment_status'),
    }


def make_handler(backend, *, admin_token=None, request_budget=None):
    """Inject backend for isolated tests; no connection created on import."""
    token = admin_token if admin_token is not None else os.getenv('SUPERDEAL_ADMIN_TOKEN', '')

    from notifications import Alerts, AlertBudget
    alert_budget = AlertBudget()
    budget = request_budget or RequestBudget()

    class Handler(BaseHTTPRequestHandler):
        server_version = 'SuperDeals'
        sys_version = ''

        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def end_headers(self):
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            super().end_headers()

        def log_message(self, format, *args):
            # No email/token/affiliate/query data in HTTP access logs.
            return

        def _peer(self):
            return client_identity(self.client_address[0], self.headers)

        def do_HEAD(self):
            return self.do_GET()

        def _limited(self):
            self.send_response(429)
            self.send_header('Retry-After', '30')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', '0')
            self.end_headers()


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
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(data)

        def do_GET(self):
            if not budget.allow(self._peer()):
                return self._limited()
            if len(self.path) > 4096:
                return self._send(414, {'error': 'request_too_long'})
            try:
                url = urlsplit(self.path)
                params = parse_qs(url.query, keep_blank_values=True, max_num_fields=16)
                if any(len(values) != 1 or len(values[0]) > 512 for values in params.values()):
                    raise ValueError('Invalid parameters')
                if url.path == '/health':
                    backend.db.command('ping')
                    return self._send(200, {'status': 'ok'})
                # Read-only legacy web contract. This adapter does not invent click counts,
                # freshness, price verification, or historical observations.
                if url.path == '/deals':
                    limit = _integer(params, 'limit', 48, 100)
                    offset = _integer(params, 'offset', 0, 2147483647)
                    snapshot = None
                    if 'as_of' in params:
                        if len(params['as_of']) != 1:
                            raise ValueError('Invalid snapshot')
                        snapshot = datetime.fromisoformat(params['as_of'][0].replace('Z', '+00:00'))
                        current = datetime.now(timezone.utc)
                        if snapshot.tzinfo is None or not current-timedelta(minutes=10) <= snapshot <= current:
                            raise ValueError('Expired pagination snapshot; refresh the feed')
                    q = params.get('q', [None])[0]
                    merchant = params.get('merchant', [None])[0]
                    min_price = _integer(params, 'min_price', 0, 1000000000) if 'min_price' in params else None
                    max_price = _integer(params, 'max_price', 0, 1000000000) if 'max_price' in params else None
                    sort = params.get('sort', ['newest'])
                    if len(sort) != 1: raise ValueError('sort must be specified once')
                    if hasattr(backend, 'legacy_search'):
                        paging = {}
                        if 'offset' in params: paging['offset'] = offset
                        if snapshot is not None: paging['at'] = snapshot
                        page = backend.legacy_search(limit=limit, q=q, merchant=merchant,
                                                     min_price=min_price, max_price=max_price, sort=sort[0], **paging)
                    else:
                        # Existing lightweight test stubs do not implement searching.
                        if set(params) & {'q', 'merchant', 'min_price', 'max_price', 'sort'}:
                            return self._send(400, {'error': 'unsupported_legacy_filters'})
                        page = backend.published_page(limit=limit, offset=offset)
                    return self._send(200, {'deals': [_legacy_deal(x, backend.public_metadata(x['id']) if hasattr(backend, 'public_metadata') else None) for x in page['items']],
                                            'counts': backend.deal_window_counts() if hasattr(backend, 'deal_window_counts') else None,
                                            'fresh_window_hours': 24 if hasattr(backend, 'public_metadata') else None, 'has_more': page['has_more'], 'as_of': page.get('as_of'), 'next_offset': page.get('next_offset')})
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
                    if not safe_destination(destination):
                        return self._send(404, {'error': 'not_found'})
                    if self.command == 'GET':
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
                return self._send(400, {'error': 'bad_request', 'detail': 'Invalid request parameters.'})
            except Exception:
                # Do not leak stack traces or secrets in HTTP responses.
                import logging
                logging.getLogger('superdeal.api').exception('HTTP API request failed')
                return self._send(500, {'error': 'internal_error'})

        def do_POST(self):
            try:
                path = urlsplit(self.path).path
            except ValueError:
                return self._send(400, {'error': 'bad_request'})
            if len(self.path) > 4096:
                return self._send(414, {'error': 'request_too_long'})
            if path not in ('/api/v1/alerts', '/api/v1/alerts/confirm', '/api/v1/alerts/stop'):
                return self._send(405, {'error': 'method_not_allowed'})
            # Never log email addresses, request bodies or bearer links.
            if not alert_budget.allow(self._peer()):
                return self._limited()
            origin = self.headers.get('Origin')
            allowed = {value.strip().rstrip('/') for value in os.getenv('SUPERDEAL_ALERT_ORIGINS', '').split(',') if value.strip()}
            if origin and origin not in allowed:
                try:
                    parsed = urlsplit(origin)
                except ValueError:
                    return self._send(403, {'error': 'Request origin is not allowed.'})
                if parsed.scheme not in ('http', 'https') or parsed.netloc != self.headers.get('Host') or parsed.path or parsed.query or parsed.fragment:
                    return self._send(403, {'error': 'Request origin is not allowed.'})
            if self.headers.get('Transfer-Encoding') or len(self.headers.get_all('Content-Length', [])) != 1:
                return self._send(400, {'error': 'A single Content-Length is required.'})
            if self.headers.get_content_type() != 'application/json':
                return self._send(415, {'error': 'Use application/json.'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096:
                    return self._send(413, {'error': 'Request is too large.'})
                self.connection.settimeout(10)
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError('Incomplete request.')
                data = json.loads(raw)
                service = Alerts(backend.db)
                # Indexes are idempotent; no pipeline startup is required for signup.
                service.setup()
                if path == '/api/v1/alerts':
                    service.subscribe(data)
                    return self._send(202, {'status': 'accepted', 'email_mode': service.mailer.mode,
                        'message': 'Request saved. Confirm your email to activate alerts.'})
                if not isinstance(data, dict) or set(data) != {'token'}:
                    raise ValueError('This link is invalid or expired.')
                success = service.confirm(data['token']) if path.endswith('/confirm') else service.stop(data['token'])
                return self._send(200 if success else 400, {'status': 'ok' if success else 'invalid_or_expired'})
            except (ValueError, UnicodeError):
                return self._send(400, {'error': 'Check the product, email, daily limit and duration, or request a new link.'})
            except Exception as exc:
                # Print only the exception type; never log recipient details or credentials.
                print('ALERT_SAVE_ERROR type=' + type(exc).__name__, flush=True)
                return self._send(503, {'error': 'Alerts are temporarily unavailable. Please try again.'})

    return Handler


def main():
    from runtime_env import load_env
    load_env()
    host = os.getenv('SUPERDEAL_API_HOST', '127.0.0.1')
    port = int(os.getenv('SUPERDEAL_API_PORT', '8765'))
    if host not in ('127.0.0.1', 'localhost', '::1') and not os.getenv('SUPERDEAL_ALLOW_REMOTE_HTTP') == '1':
        raise RuntimeError('Remote HTTP bind requires explicit SUPERDEAL_ALLOW_REMOTE_HTTP=1 and TLS reverse proxy')
    if not os.getenv('SUPERDEAL_ADMIN_TOKEN', '').strip():
        raise RuntimeError('SUPERDEAL_ADMIN_TOKEN must be configured before API startup')
    if os.getenv('SUPERDEAL_PRODUCTION') == '1':
        from http_security import production_errors
        errors = production_errors(host)
        if errors:
            raise RuntimeError('; '.join(errors))
    backend = connect()
    backend.setup_public()
    server = BoundedHTTPServer((host, port), make_handler(backend))
    print(f'SuperDeal API: http://{host}:{port}')
    server.serve_forever()


if __name__ == '__main__':
    main()
