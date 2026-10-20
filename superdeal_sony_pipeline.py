"""Explicit, one-shot manual deal: Mongo raw -> EarnKaro -> Mistral -> validated facts.

No Telegram listener, retries, or publication. Never prints credentials or response bodies.
"""
import argparse
import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'superdeal_phase2_full'))
from backend import connect
from superdeal_earnkaro_one_shot import execute as earnkaro_execute, load_key
from superdeal_mistral_one_shot import run as mistral_run

MESSAGE = ("Sony WF-C710NSA | Dual Noise Cancellation Wireless Bluetooth Earbud @3891\n\n"
           "500 Cpn + 2099 OFF Via SBI CC / DC\n\n"
           "https://amzn-to.co/QYJhfJ")
CHANNEL = 'manual:test'
MESSAGE_ID = 'sony-wf-c710nsa-' + hashlib.sha256(MESSAGE.encode('utf-8')).hexdigest()[:20]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--confirm-run', action='store_true', help='Authorize one live EarnKaro request and local Mistral inference')
    a = p.parse_args()
    if not a.confirm_run:
        p.error('No database changes or API calls made; add --confirm-run')
    key = load_key()  # fail before ingestion if not configured
    backend = connect()
    backend.setup()
    existing = backend.db.raw.find_one({'channel': CHANNEL, 'message_id': MESSAGE_ID})
    if existing:
        rid = existing['_id']
        state = backend.db.pipeline_status.find_one({'raw_id': rid}) or {}
        print('EXISTING raw ID:', rid, 'stage:', state.get('current_stage'), 'status:', state.get('status'))
        print('No automatic retry or duplicate processing.')
        return 2
    rid = backend.ingest(CHANNEL, MESSAGE_ID, MESSAGE)
    print('RAW_STORED:', rid, 'source:', CHANNEL, 'message_id:', MESSAGE_ID, flush=True)

    def converter(text):
        old = os.environ.get('API_KEY_EARNKARO')
        os.environ['API_KEY_EARNKARO'] = key
        try:
            return backend._earnkaro(text)
        finally:
            if old is None:
                os.environ.pop('API_KEY_EARNKARO', None)
            else:
                os.environ['API_KEY_EARNKARO'] = old

    earnkaro_execute(backend, rid, converter=converter)
    print('EARNKARO_COMPLETE: full JSON response stored in ek_raw', flush=True)
    count = mistral_run(backend, rid)
    print('PASS:', count, 'validated fact(s) in fact_table; NOT PUBLISHED')
    print('RAW_ID:', rid)
    print('STAGE: VALIDATED_AWAITING_APPROVAL')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print('FAILED:', type(exc).__name__, '- no automatic retry or publication', file=sys.stderr)
        sys.exit(1)
