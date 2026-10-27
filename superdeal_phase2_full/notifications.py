"""Opt-in MongoDB deal alerts. No SMTP or background work on import."""
from __future__ import annotations
import hashlib
import json
import os
import pathlib
import re
import secrets
import smtplib
import ssl
import threading
import time
import unicodedata
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlsplit
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

UTC = timezone.utc
IST = timezone(timedelta(hours=5, minutes=30))
ACCESSORIES = {'case', 'cover', 'protector', 'glass', 'cable', 'charger', 'adapter', 'skin', 'lens', 'holder', 'stand', 'strap', 'screen', 'replacement', 'refurbished', 'renewed', 'cases', 'covers', 'protectors', 'cables', 'chargers', 'adapters', 'skins', 'holders', 'straps'}


def tokens(text):
    text = unicodedata.normalize('NFKC', text).casefold()
    # iPhone17 / iPhone 17, and ProMax / Pro Max normalize consistently.
    text = re.sub(r'promax\b', 'pro max', text)
    return re.findall(r'[^\W\d_]+|\d+', text, re.UNICODE)


def matches(query, title):
    """Match one unique word for a one-word request, otherwise at least two.

    Match normalized complete tokens only; duplicates never increase the score.
    This intentionally allows broader model/accessory matches for initial alerts.
    """
    wanted, actual = set(tokens(query)), set(tokens(title))
    if not wanted:
        return False
    required = min(2, len(wanted))
    return len(wanted & actual) >= required


def validate_request(data):
    if not isinstance(data, dict) or set(data) != {'product', 'email', 'daily_limit', 'days', 'consent'}:
        raise ValueError('Complete all fields.')
    product, email = data['product'], data['email']
    if not isinstance(product, str) or not 3 <= len(product.strip()) <= 120 or re.search(r'[\x00-\x1f<>@]|https?://', product, re.I):
        raise ValueError('Enter a product name between 3 and 120 characters.')
    product = ' '.join(product.split())
    if not tokens(product):
        raise ValueError('Enter a product name, for example Headphones.')
    if not isinstance(email, str) or len(email) > 254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}", email.strip()):
        raise ValueError('Enter a valid email address.')
    if type(data['daily_limit']) is not int or data['daily_limit'] not in (1, 2, 3, 5):
        raise ValueError('Choose 1, 2, 3 or 5 emails per day.')
    if type(data['days']) is not int or not 1 <= data['days'] <= 30:
        raise ValueError('Choose between 1 and 30 days.')
    if data['consent'] is not True:
        raise ValueError('Please agree to receive these deal alerts.')
    return product, email.strip().casefold(), data['daily_limit'], data['days']


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class AlertBudget:
    """Bounded local request limiter; does not trust forwarding headers."""
    def __init__(self):
        self.peers = OrderedDict()
        self.lock = threading.Lock()

    def allow(self, peer):
        at = time.monotonic()
        with self.lock:
            count, start = self.peers.pop(peer, (0, at))
            if at - start >= 3600:
                count, start = 0, at
            self.peers[peer] = (count + 1, start)
            while len(self.peers) > 4096:
                self.peers.popitem(last=False)
            return count < 12


class Mailer:
    """Dry-run by default. Preview files are private and never served by the API."""
    def __init__(self):
        self.mode = os.getenv('SUPERDEAL_EMAIL_MODE', 'dry-run')
        self.origin = os.getenv('SUPERDEAL_PUBLIC_URL', 'http://localhost:5174').rstrip('/')
        parsed = urlsplit(self.origin)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise ValueError('SUPERDEAL_PUBLIC_URL must be an origin only.')
        self.sender = os.getenv('SUPERDEAL_EMAIL_FROM', 'SuperDeals <alerts@superdeals.invalid>')
        if self.mode not in ('dry-run', 'smtp'):
            raise ValueError('Unknown email mode.')
        if self.mode == 'smtp':
            if parsed.scheme != 'https' or '.invalid' in self.sender or '\n' in self.sender or '\r' in self.sender:
                raise ValueError('SMTP requires HTTPS and a real sender address.')
            if not all(os.getenv(k) for k in ('SUPERDEAL_SMTP_HOST', 'SUPERDEAL_SMTP_USER', 'SUPERDEAL_SMTP_PASSWORD')):
                raise ValueError('SMTP credentials are not configured.')

    def send(self, email, subject, body):
        msg = EmailMessage()
        msg['From'], msg['To'], msg['Subject'] = self.sender, email, subject
        msg.set_content(body)
        if self.mode == 'dry-run':
            folder = pathlib.Path(os.getenv('SUPERDEAL_EMAIL_PREVIEW_DIR', 'data/notification-previews'))
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = folder / (secrets.token_hex(16) + '.eml')
            with path.open('x', encoding='utf-8') as handle:
                os.chmod(path, 0o600)
                handle.write(msg.as_string())
            return 'previewed'
        # Require encrypted authenticated SMTP; never fall back to cleartext.
        host, port = os.environ['SUPERDEAL_SMTP_HOST'], int(os.getenv('SUPERDEAL_SMTP_PORT', '587'))
        with smtplib.SMTP(host, port, timeout=20) as client:
            client.ehlo()
            client.starttls(context=ssl.create_default_context())
            client.ehlo()
            client.login(os.environ['SUPERDEAL_SMTP_USER'], os.environ['SUPERDEAL_SMTP_PASSWORD'])
            client.send_message(msg)
        return 'sent'


class Alerts:
    def __init__(self, db, mailer=None):
        self.db = db
        self.mailer = mailer or Mailer()

    def setup(self):
        self.db.deal_alerts.create_index([('email', 1), ('status', 1), ('expires_at', 1)])
        self.db.deal_alerts.create_index('confirm_hash', unique=True, sparse=True)
        self.db.deal_alerts.create_index('stop_hash', unique=True, sparse=True)
        self.db.deal_alerts.create_index([('status', 1), ('next_due', 1)])
        for name in ('deal_alerts', 'alert_confirmations', 'alert_deliveries'):
            self.db[name].create_index('purge_at', expireAfterSeconds=0)

    def subscribe(self, data, *, at=None):
        product, email, cap, days = validate_request(data)
        at = at or datetime.now(UTC)
        key = digest(email + '\n' + ' '.join(tokens(product)))
        existing = self.db.deal_alerts.find_one({'_id': key})
        if existing and existing['status'] in ('pending', 'active') and existing['expires_at'].replace(tzinfo=UTC) > at:
            return  # No preference changes or repeated confirmation spam.
        if self.db.deal_alerts.count_documents({'email': email, 'status': {'$in': ['pending', 'active']}, 'expires_at': {'$gt': at}}) >= 5:
            return  # Generic response prevents address enumeration.
        confirm, stop = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        doc = {'product': product, 'email': email, 'daily_limit': cap, 'days': days,
               'status': 'pending', 'created_at': at, 'expires_at': at + timedelta(hours=24),
               'purge_at': at + timedelta(days=31), 'confirm_hash': digest(confirm),
               'stop_hash': digest(stop), 'stop_token': stop, 'consent_at': at,
               'consent_version': 'deal-alerts-v1', 'next_due': at, 'lease_until': at,
               'day': '', 'daily_count': 0}
        # Atomic replacement gate prevents parallel form submits resetting a live alert.
        if existing:
            result = self.db.deal_alerts.update_one({'_id': key, '$or': [{'status': {'$in': ['stopped', 'expired']}}, {'expires_at': {'$lte': at}}]}, {'$set': doc})
            if not result.modified_count:
                return
        else:
            try:
                self.db.deal_alerts.insert_one({'_id': key, **doc})
            except DuplicateKeyError:
                return
        self.db.alert_confirmations.insert_one({'alert_id': key, 'confirm_token': confirm,
            'state': 'queued', 'created_at': at, 'purge_at': at + timedelta(days=2)})

    def confirm(self, token, *, at=None):
        self._token(token)
        at = at or datetime.now(UTC)
        doc = self.db.deal_alerts.find_one({'confirm_hash': digest(token), 'status': 'pending', 'expires_at': {'$gt': at}})
        if not doc:
            return False
        end = at + timedelta(days=doc['days'])
        return bool(self.db.deal_alerts.update_one({'_id': doc['_id'], 'status': 'pending', 'confirm_hash': digest(token), 'expires_at': {'$gt': at}},
            {'$set': {'status': 'active', 'verified_at': at, 'expires_at': end, 'purge_at': end + timedelta(days=30)}, '$unset': {'confirm_hash': ''}}).modified_count)

    def stop(self, token):
        self._token(token)
        result = self.db.deal_alerts.update_one({'stop_hash': digest(token)}, {'$set': {'status': 'stopped'}, '$unset': {'confirm_hash': ''}})
        return bool(result.matched_count)

    @staticmethod
    def _token(value):
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{40,60}', value):
            raise ValueError('This link is invalid or expired.')

    def run_once(self, backend, *, at=None):
        """Dispatch is disabled unless explicitly enabled by the operator."""
        if os.getenv('SUPERDEAL_ALERT_DISPATCH_ENABLED') != '1':
            return {'confirmations': 0, 'batches': 0, 'failed': 0}
        test_at = at
        clock = (lambda: test_at) if test_at is not None else (lambda: datetime.now(UTC))
        at = clock()
        stats = {'confirmations': 0, 'batches': 0, 'failed': 0}
        for _ in range(100):
            at = clock()
            queued = self.db.alert_confirmations.find_one_and_update({'state': 'queued'}, {'$set': {'state': 'sending'}}, return_document=ReturnDocument.AFTER)
            if not queued:
                break
            alert = self.db.deal_alerts.find_one({'_id': queued['alert_id'], 'confirm_hash': digest(queued['confirm_token']), 'status': 'pending', 'expires_at': {'$gt': at}})
            if not alert:
                self.db.alert_confirmations.delete_one({'_id': queued['_id']})
                continue
            body = (f"Confirm your SuperDeals alert for {alert['product']}.\n"
                    f"Up to {alert['daily_limit']} emails per day for {alert['days']} days, only when a matching deal is available.\n\n"
                    f"{self.mailer.origin}/#alert_confirm={queued['confirm_token']}\n\n"
                    "If you did not request this, ignore this email. The request expires in 24 hours.\n"
                    f"Cancel this request: {self.mailer.origin}/#alert_stop={alert['stop_token']}\n")
            try:
                self.mailer.send(alert['email'], 'Confirm your SuperDeals deal alert', body)
                stats['confirmations'] += 1
                self.db.alert_confirmations.delete_one({'_id': queued['_id']})
            except Exception:
                self.db.alert_confirmations.update_one({'_id': queued['_id']}, {'$set': {'state': 'failed'}, '$unset': {'confirm_token': ''}})
                stats['failed'] += 1
        self.db.deal_alerts.update_many({'status': {'$in': ['active', 'pending']}, 'expires_at': {'$lte': at}}, {'$set': {'status': 'expired'}})
        day = at.astimezone(IST).date().isoformat()
        # Each alert is claimed once per cycle, and exclusive leases coordinate workers.
        for _ in range(100):
            at = clock()
            day = at.astimezone(IST).date().isoformat()
            claim = secrets.token_hex(16)
            alert = self.db.deal_alerts.find_one_and_update({'status': 'active', 'expires_at': {'$gt': at}, 'next_due': {'$lte': at}, 'lease_until': {'$lte': at}},
                {'$set': {'lease_until': at + timedelta(minutes=10), 'claim': claim, 'next_due': at + timedelta(minutes=5)}}, return_document=ReturnDocument.AFTER)
            if not alert:
                break
            try:
                if alert['day'] == day and alert['daily_count'] >= alert['daily_limit']:
                    continue
                deals = []
                for deal in backend.notification_candidates(at=at, window=timedelta(seconds=359)):
                    from public_presentation import shopper_text
                    title = shopper_text(deal.get('product_name') or '')
                    if not matches(alert['product'], title):
                        continue
                    key = digest(alert['_id'] + ':' + str(deal['id']))
                    if self.db.alert_deliveries.find_one({'_id': key}):
                        continue
                    deals.append((key, deal, title))
                    if len(deals) == 10:
                        break
                if not deals:
                    continue
                self.db.deal_alerts.update_one({'_id': alert['_id'], 'claim': claim, 'day': {'$ne': day}}, {'$set': {'day': day, 'daily_count': 0}})
                # Atomic quota reservation also rechecks cancellation/expiry before dispatch.
                dispatch_at = clock()
                reserved = self.db.deal_alerts.update_one({'_id': alert['_id'], 'claim': claim, 'status': 'active', 'expires_at': {'$gt': dispatch_at}, 'lease_until': {'$gt': dispatch_at}, 'day': day, 'daily_count': {'$lt': alert['daily_limit']}},
                    {'$inc': {'daily_count': 1}, '$set': {'next_due': at + timedelta(seconds=86400 / alert['daily_limit'])}})
                if not reserved.modified_count:
                    continue
                selected = []
                for key, deal, title in deals:
                    try:
                        self.db.alert_deliveries.insert_one({'_id': key, 'alert_id': alert['_id'], 'deal_id': str(deal['id']), 'state': 'reserved', 'created_at': at, 'purge_at': at + timedelta(days=60)})
                        selected.append((key, deal, title))
                    except DuplicateKeyError:
                        pass
                if not selected:
                    continue
                from urllib.parse import quote
                lines = [f"Matching deals for {alert['product']}", '']
                for _, deal, title in selected:
                    price = deal.get('deal_price')
                    lines += [title, f'Price: INR {price}' if isinstance(price, (int, float)) and not isinstance(price, bool) and price > 0 else 'View price at retailer',
                              f"{self.mailer.origin}/go/{quote(str(deal['id']), safe='')}", '']
                lines += ['Confirm price, availability and conditions at the retailer.',
                          f"Stop these alerts: {self.mailer.origin}/#alert_stop={alert['stop_token']}"]
                outcome = self.mailer.send(alert['email'], 'SuperDeals: matching product deals', '\n'.join(lines))
                self.db.alert_deliveries.update_many({'_id': {'$in': [x[0] for x in selected]}}, {'$set': {'state': outcome}})
                stats['batches'] += 1
            except Exception:
                # No exception text or recipient data in logs. Reservations remain for review.
                stats['failed'] += 1
            finally:
                self.db.deal_alerts.update_one({'_id': alert['_id'], 'claim': claim}, {'$set': {'lease_until': at}, '$unset': {'claim': ''}})
        return stats


def main():
    from runtime_env import load_env
    load_env()
    import argparse
    from backend import connect
    parser = argparse.ArgumentParser(description='Process opt-in alerts; dry-run by default.')
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()
    backend = connect()
    service = Alerts(backend.db)
    service.setup()
    while True:
        print(json.dumps(service.run_once(backend)), flush=True)
        if args.once:
            return
        time.sleep(12 * 60 * 60)


if __name__ == '__main__':
    main()
