"""Read-only local inspection of private MongoDB notification requests."""
import argparse
import json
from datetime import datetime, timezone

FIELDS = ('product', 'email', 'daily_limit', 'days', 'status', 'created_at',
          'verified_at', 'expires_at', 'daily_count', 'day')

def mask_email(email):
    if not isinstance(email, str) or '@' not in email:
        return None
    local, domain = email.rsplit('@', 1)
    return local[:1] + '***@' + domain

def list_requests(db, *, limit=20, email=None, at=None):
    if not 1 <= limit <= 100:
        raise ValueError('Choose a limit from 1 to 100.')
    at = at or datetime.now(timezone.utc)
    query = {'email': email.strip().casefold()} if email else {}
    projection = {key: 1 for key in FIELDS}
    projection['_id'] = 0
    output = []
    for row in db.deal_alerts.find(query, projection).sort('created_at', -1).limit(limit):
        item = {key: row.get(key) for key in FIELDS}
        item['email'] = mask_email(item['email'])
        expires = item.get('expires_at')
        if expires and expires.replace(tzinfo=timezone.utc) <= at and item['status'] in ('pending','active'):
            item['status'] = 'expired'
        output.append(item)
    return output

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--limit',type=int,default=20)
    parser.add_argument('--email',help='Filter locally by one exact recipient address')
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error('--limit must be between 1 and 100')
    from backend import connect
    backend = connect()  # Loads repository .env; no setup, writes or sends.
    try:
        print(json.dumps({'requests':list_requests(backend.db,limit=args.limit,email=args.email)},default=str,indent=2,ensure_ascii=False))
    finally:
        backend.db.client.close()

if __name__ == '__main__':
    main()
