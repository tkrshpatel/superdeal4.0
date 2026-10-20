"""One-shot local Mistral extraction from an existing EarnKaro MongoDB response.

No EarnKaro/Telegram calls, no retries, and NO publication.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'superdeal_phase2_full'))


def run(backend, raw_id):
    from backend import now, urls

    db = backend.db
    ek = db.ek_raw.find_one({'raw_id': raw_id})
    if ek is None:
        raise RuntimeError('No stored EarnKaro response for selected raw ID')
    body = ek.get('response_payload')
    text = ek.get('response_text')
    if not isinstance(body, dict) or not isinstance(body.get('data'), str) or text != body['data'] or not text.strip():
        raise RuntimeError('Stored EarnKaro response is missing or inconsistent')
    status = db.pipeline_status.find_one({'raw_id': raw_id})
    if not status or status.get('status') != 'PROCESSING' or status.get('current_stage') != 'EARNKARO_COMPLETE':
        raise RuntimeError('Stage not ready; no retries or duplicate execution')
    if db.fact_table.count_documents({'raw_id': raw_id}):
        raise RuntimeError('Facts already exist; refusing to overwrite')
    claimed = db.pipeline_status.update_one(
        {'raw_id': raw_id, 'status': 'PROCESSING', 'current_stage': 'EARNKARO_COMPLETE'},
        {'$set': {'current_stage': 'LLM', 'updated_at': now()}})
    if claimed.modified_count != 1:
        raise RuntimeError('Could not exclusively claim LLM stage')

    stage = 'LLM'
    try:
        backend.log(raw_id, stage, 'INFO', 'STAGE_STARTED')
        llm_response = backend._ollama(text)
        stage = 'VALIDATION'
        parsed = backend.validate(llm_response, text)
        # Exact response text is authoritative; check that it was preserved in
        # the complete EarnKaro response, not only a reconstructed snippet.
        allowed = urls(body['data'])
        proposed = [u for p in parsed['products'] for u in p['affiliate_urls']]
        if len(proposed) != len(set(proposed)) or set(proposed) != allowed:
            raise ValueError('EarnKaro URL provenance validation failed')
        # Save all facts atomically; never create a publication_id or PUBLISHED state.
        with db.client.start_session() as session:
            with session.start_transaction():
                if db.fact_table.count_documents({'raw_id': raw_id}, session=session):
                    raise RuntimeError('Facts appeared during processing')
                for index, product in enumerate(parsed['products']):
                    db.fact_table.insert_one({
                        'raw_id': raw_id, 'offer_index': index,
                        'product': product, 'llm_response': llm_response,
                        'model': os.getenv('OLLAMA_MODEL', 'mistral:instruct'),
                        'created_at': now(),
                    }, session=session)
                result = db.pipeline_status.update_one(
                    {'raw_id': raw_id, 'status': 'PROCESSING', 'current_stage': 'LLM'},
                    {'$set': {'current_stage': 'VALIDATED_AWAITING_APPROVAL',
                              'products_extracted': len(parsed['products']),
                              'products_published': 0, 'updated_at': now()}},
                    session=session)
                if result.modified_count != 1:
                    raise RuntimeError('Could not commit validated facts and status')
        backend.log(raw_id, stage, 'INFO', 'VALIDATED_NOT_PUBLISHED',
                    details={'products': len(parsed['products'])})
        return len(parsed['products'])
    except Exception as exc:
        backend._fail(raw_id, stage, exc)
        raise RuntimeError('Mistral extraction/validation failed; no retry or publication (details withheld)') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw-id', required=True)
    parser.add_argument('--confirm-extract', action='store_true',
                        help='Authorize one local Mistral inference and MongoDB fact write')
    args = parser.parse_args()
    if not args.confirm_extract:
        parser.error('No inference performed. Add --confirm-extract to proceed.')
    from bson import ObjectId
    from backend import connect
    try:
        raw_id = ObjectId(args.raw_id)
    except Exception:
        parser.error('--raw-id must be a 24-character MongoDB ObjectId')
    backend = connect()
    backend.setup()
    count = run(backend, raw_id)
    print(f'PASS: {count} product fact(s) validated and saved; NOT PUBLISHED')
    print('Raw ID:', raw_id)
    print('Stage: VALIDATED_AWAITING_APPROVAL')
    print('No EarnKaro requests, Telegram monitoring, retries or publication.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('FAILED:', type(exc).__name__, '- no automatic retry or publication', file=sys.stderr)
        sys.exit(1)
