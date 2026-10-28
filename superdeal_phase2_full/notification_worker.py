"""Scheduled delivery for consented notification_table requests; opt-in only."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from notifications import Mailer, tokens, digest, IST
from public_presentation import shopper_text

UTC = timezone.utc
INTERVAL = timedelta(hours=12)
LOOKBACK = timedelta(hours=11, minutes=59)


def matches_request(query, title):
    wanted, actual = set(tokens(query)), set(tokens(title))
    return bool(wanted) and len(wanted & actual) >= (1 if len(wanted) == 1 else 2)


def aware(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def candidates(backend, at):
    # Same committed publication gate as the website; edits/raw capture are not publications.
    pipeline = [s for s in backend._published_pipeline(limit=1) if '$limit' not in s]
    pipeline.insert(-1, {'$match': {'_publication.published_at': {
        '$gte': at - LOOKBACK, '$lte': at}}})
    for doc in backend.db.fact_table.aggregate(pipeline):
        yield {'id': str(doc['_id']), **doc['product'], **backend._offer_fields(doc)}


class NotificationWorker:
    def __init__(self, db, mailer):
        self.db, self.mailer = db, mailer

    def setup(self):
        self.db.notification_deliveries.create_index([('request_id', 1), ('created_at', -1)])
        self.db.notification_table.create_index([('status', 1), ('expires_at', 1)])

    def run_once(self, backend, *, at=None, deals=None):
        clock = (lambda: at) if at is not None else (lambda: datetime.now(UTC))
        started = clock()
        stats = {'sent': 0, 'failed': 0, 'skipped': 0}
        # Durable schedule coordinates multiple processes and survives restarts.
        state = self.db.notification_worker_state
        try:
            state.insert_one({'_id': 'schedule', 'next_run': started})
        except DuplicateKeyError:
            pass
        claimed = state.find_one_and_update({'_id': 'schedule', 'next_run': {'$lte': started}},
            {'$set': {'next_run': started + INTERVAL, 'last_started': started}},
            return_document=ReturnDocument.AFTER)
        if not claimed:
            return {**stats, 'not_due': True}
        pool = list(candidates(backend, started) if deals is None else deals)
        for request in self.db.notification_table.find({'status': {'$in': ['saved', 'active']}, 'consent': True}):
            current = clock()
            end = request.get('expires_at') or (aware(request['ds']) + timedelta(days=request['days']))
            end = aware(end)
            version = {'_id': request['_id'], 'ds': request['ds'],
                       'status': {'$in': ['saved', 'active']}, 'consent': True}
            if end <= current:
                self.db.notification_table.update_one(version, {'$set': {'status': 'expired', 'expires_at': end}})
                continue
            matched = [d for d in pool if matches_request(request['product'], shopper_text(d.get('product_name') or ''))]
            if not matched:
                continue
            selected = []
            batch = digest(str(request['_id']) + ':' + started.isoformat())
            try:
                # Reserve deal identities permanently before SMTP; uncertain sends never retry.
                for deal in matched:
                    key = digest(str(request['_id']) + ':' + str(deal['id']))
                    try:
                        self.db.notification_deliveries.insert_one({'_id': key, 'request_id': request['_id'],
                            'deal_id': str(deal['id']), 'batch': batch, 'state': 'reserved', 'created_at': current})
                        selected.append(deal)
                    except DuplicateKeyError:
                        pass
                if not selected:
                    continue
                current = clock()
                day = current.astimezone(IST).date().isoformat()
                self.db.notification_table.update_one({**version, 'delivery_day': {'$ne': day}},
                    {'$set': {'delivery_day': day, 'daily_count': 0}})
                # Atomic quota and fresh consent/expiry/submission checks immediately before send.
                eligible = {**version, 'delivery_day': day, 'daily_count': {'$lt': request['daily_limit']}}
                if end <= current or not self.db.notification_table.update_one(eligible,
                    {'$inc': {'daily_count': 1}, '$set': {'expires_at': end, 'last_attempt_at': current}}).modified_count:
                    # No SMTP attempted: remove only this batch's reservations for a later cycle.
                    self.db.notification_deliveries.delete_many({'batch': batch, 'state': 'reserved'})
                    stats['skipped'] += 1
                    continue
                lines = [f"Deals matching your request: {shopper_text(request['product'])}", '']
                for deal in selected:
                    title = shopper_text(deal.get('product_name') or '')
                    facts = deal.get('offer_facts')
                    price = facts.get('current_price') if facts else deal.get('deal_price')
                    valid = isinstance(price, (int, float)) and not isinstance(price, bool) and price > 0
                    lines += [title, f'INR {price:,.2f}' if valid else 'View price at retailer',
                              f"{self.mailer.origin}/go/{quote(str(deal['id']), safe='')}", '']
                lines += ['Confirm final prices, availability and offer conditions at the retailer.',
                          'To stop alerts, reply STOP to this email with your product request.']
                outcome = self.mailer.send(request['email'], 'SuperDeals: deals for your product', '\n'.join(lines))
                self.db.notification_deliveries.update_many({'batch': batch},
                    {'$set': {'state': outcome, 'finished_at': clock()}})
                stats['sent' if outcome == 'sent' else 'skipped'] += 1
            except Exception as exc:
                # Failure may happen after SMTP accepted a message. Never automatically resend.
                self.db.notification_deliveries.update_many({'batch': batch, 'state': 'reserved'},
                    {'$set': {'state': 'failed_or_unknown', 'error_type': type(exc).__name__, 'finished_at': clock()}})
                stats['failed'] += 1
        state.update_one({'_id': 'schedule'}, {'$set': {'last_finished': clock(), 'last_stats': stats}})
        return stats


def main():
    from runtime_env import load_env
    from backend import connect
    load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--stop-email', help='Stop consented requests for this exact recipient; no SMTP.')
    args = parser.parse_args()
    if os.getenv('SUPERDEAL_NOTIFICATIONS_ENABLED') != '1':
        raise ValueError('Set SUPERDEAL_NOTIFICATIONS_ENABLED=1 to enable the notification worker.')
    backend = connect()
    if args.stop_email:
        result = backend.db.notification_table.update_many({'email': args.stop_email.strip().casefold()},
            {'$set': {'status': 'stopped', 'consent': False}})
        print(json.dumps({'stopped': result.modified_count}))
        return
    mailer = Mailer()
    if mailer.mode != 'smtp':
        raise ValueError('Notification delivery requires SUPERDEAL_EMAIL_MODE=smtp.')
    worker = NotificationWorker(backend.db, mailer)
    worker.setup()
    nonce = os.environ.pop('SUPERDEAL_LAUNCH_NONCE', '')
    if nonce:
        path = Path(__file__).resolve().parents[1]/'data'/'launcher-notifications-ready.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'nonce': nonce, 'pid': os.getpid()}), encoding='utf-8')
        temporary.replace(path)
    print('READY: notification worker; 12-hour schedule', flush=True)
    while True:
        try:
            print(json.dumps(worker.run_once(backend)), flush=True)
        except Exception as exc:
            print(json.dumps({'notification_error': type(exc).__name__}), flush=True)
        if args.once:
            return
        time.sleep(60)


if __name__ == '__main__':
    main()
