"""Explicit one-shot EarnKaro stage for a single MongoDB raw record.

Does NOT call Mistral, publish, poll Telegram, or retry failures.
"""
import argparse
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

from bson import ObjectId

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'superdeal_phase2_full'))
from backend import connect


def utcnow():
    return datetime.now(timezone.utc)


def load_key():
    key = os.getenv('API_KEY_EARNKARO', '').strip()
    if key:
        return key
    envfile = ROOT / '.env'
    if envfile.is_file():
        for line in envfile.read_text(encoding='utf-8-sig').splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or '=' not in stripped:
                continue
            name, value = stripped.split('=', 1)
            if name.strip() == 'API_KEY_EARNKARO':
                return value.strip().strip('"\'').strip()
    raise RuntimeError('API_KEY_EARNKARO not configured in environment or project .env')


def execute(backend, raw_id, *, converter):
    db = backend.db
    raw = db.raw.find_one({'_id': raw_id})
    if raw is None:
        raise ValueError('Selected raw record not found')
    if db.ek_raw.find_one({'raw_id': raw_id}) is not None:
        raise RuntimeError('EarnKaro response already exists; no repeat request')
    claim = db.pipeline_status.update_one(
        {'raw_id': raw_id, 'status': 'PENDING'},
        {'$set': {'status': 'PROCESSING', 'current_stage': 'EARNKARO', 'updated_at': utcnow()}})
    if claim.modified_count != 1:
        raise RuntimeError('Record is not PENDING; no retry or repeat permitted')
    try:
        backend.log(raw_id, 'EARNKARO', 'INFO', 'STAGE_STARTED')
        result = converter(raw['text'])
        if not isinstance(result, dict) or not isinstance(result.get('response_payload'), dict):
            raise ValueError('Invalid EarnKaro response payload')
        response_text = result['response_payload'].get('data')
        if not isinstance(response_text, str) or not response_text.strip():
            raise ValueError('EarnKaro response contains no converted text')
        # Preserve the full parsed JSON body, including exact unstripped data string.
        db.ek_raw.insert_one({'raw_id': raw_id, 'response_text': response_text,
                              'response_payload': result['response_payload'], 'created_at': utcnow()})
        db.pipeline_status.update_one({'raw_id': raw_id, 'status': 'PROCESSING'},
            {'$set': {'current_stage': 'EARNKARO_COMPLETE', 'updated_at': utcnow()}})
        backend.log(raw_id, 'EARNKARO', 'INFO', 'CONVERTED')
        return True
    except Exception as exc:
        backend._fail(raw_id, 'EARNKARO', exc)
        raise RuntimeError('EarnKaro stage failed; no automatic retry (details withheld)') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-id', required=True, help='Exact MongoDB raw record ID')
    parser.add_argument('--confirm-convert', action='store_true', help='Authorize exactly one live EarnKaro request')
    args = parser.parse_args()
    if not args.confirm_convert:
        parser.error('No API request made. Add --confirm-convert to authorize one conversion.')
    try:
        raw_id = ObjectId(args.raw_id)
    except Exception:
        parser.error('--raw-id must be a valid 24-character MongoDB ObjectId')
    # Never print or log the credential.
    key = load_key()
    backend = connect()
    backend.setup()
    def converter(text):
        # Same request shape as the existing MongoDB backend; key is supplied only here.
        old = os.environ.get('API_KEY_EARNKARO')
        os.environ['API_KEY_EARNKARO'] = key
        try:
            return backend._earnkaro(text)
        finally:
            if old is None:
                os.environ.pop('API_KEY_EARNKARO', None)
            else:
                os.environ['API_KEY_EARNKARO'] = old
    execute(backend, raw_id, converter=converter)
    print('PASS: EarnKaro response saved to ek_raw; stage=EARNKARO_COMPLETE')
    print('Raw ID:', raw_id)
    print('No Mistral, publication, Telegram monitoring, or automatic retries.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('FAILED:', type(exc).__name__, '- no automatic retry; check sanitized pipeline status', file=sys.stderr)
        sys.exit(1)
