"""Find and optionally replay ONE saved published EarnKaro deal with terms.

Runs locally against your existing MongoDB. No new EarnKaro/LLM/merchant calls.
Original facts and raw records are unchanged. Uses the normal publication gate.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'superdeal_phase2_full'))
from backend import Backend, connect, urls
from affiliate_link_ids import link_map
from deal_terms import extract_deal_terms


def choose_saved_deal(db, *, limit=500):
    """Only replay a complete single-product publication with exact URL coverage."""
    for saved in db.ek_raw.find({}).sort('created_at', -1).limit(limit):
        raw_id = saved.get('raw_id')
        status = db.pipeline_status.find_one({'raw_id':raw_id, 'status':'PUBLISHED'})
        if not status or status.get('products_published') != 1 or not status.get('publication_id'):
            continue
        facts = list(db.fact_table.find({'raw_id':raw_id, 'publication_id':status['publication_id']}))
        if len(facts) != 1:
            continue
        fact=facts[0]
        product=fact.get('product') or {}
        if str(product.get('product_name','')).startswith('[ARCHIVED PREVIEW '):
            continue
        text=saved.get('response_text','')
        if not isinstance(text,str) or len(urls(text)) != 1 or set(product.get('affiliate_urls') or []) != urls(text):
            continue
        terms=extract_deal_terms(text,[product])[0]
        if not terms or not (terms['has_coupon'] or terms['instructions'] or terms['conditions']):
            continue
        return {'saved':saved, 'fact':fact, 'terms':terms}
    return None


def replay_response(candidate, token):
    """Reformat a stored product into the pipeline's opaque-ID schema."""
    product=deepcopy(candidate['fact']['product'])
    product['product_name']=f"[ARCHIVED PREVIEW {token}] {product['product_name']}"
    mapping=link_map(candidate['saved']['response_text'])
    reverse={url:identifier for identifier,url in mapping.items()}
    product['link_ids']=[reverse[u] for u in product.pop('affiliate_urls')]
    return json.dumps({'products':[product], 'unassigned_link_ids':[],
                      'message_issues':['Archived preview; price, code and eligibility may have expired.'],
                      'analysis_summary':'Replay of stored EarnKaro evidence, with a unique preview name.'})


def publish_replay(db, candidate):
    token=uuid4().hex[:8]
    response=replay_response(candidate,token)
    text=candidate['saved']['response_text']
    image=(candidate['fact'].get('image_enrichment') or {}).get('image_url')
    backend=Backend(db, converter=lambda _: {'response_text':text, 'response_payload':{'replayed_from':str(candidate['saved']['_id'])}},
                    llm=lambda _:response, image_scraper=lambda _:image)
    backend.setup()
    # Only this process skips research; the running worker's environment is unaffected.
    previous=os.environ.get('SUPERDEAL_PRE_LLM_RESEARCH')
    os.environ['SUPERDEAL_PRE_LLM_RESEARCH']='0'
    try:
        raw_id=backend.ingest('LOCAL_ARCHIVED_PREVIEW',token,text)
        backend.db.raw.update_one({'_id':raw_id},{'$set':{'preview_source_raw_id':candidate['saved']['raw_id'], 'is_archived_preview':True}})
        backend.process(raw_id)
    finally:
        if previous is None: os.environ.pop('SUPERDEAL_PRE_LLM_RESEARCH',None)
        else: os.environ['SUPERDEAL_PRE_LLM_RESEARCH']=previous
    status=db.pipeline_status.find_one({'raw_id':raw_id}) or {}
    if status.get('status') != 'PUBLISHED':
        raise RuntimeError(f"Preview not published: {status.get('status')} at {status.get('current_stage')}")
    offers=list(db.fact_table.find({'raw_id':raw_id, 'publication_id':status['publication_id']}))
    if len(offers)!=1 or offers[0].get('deal_terms') != candidate['terms']:
        raise RuntimeError('Preview terms verification failed')
    public=backend.published_offer_by_id(str(offers[0]['_id']))
    if not public or public.get('deal_terms')!=candidate['terms']:
        raise RuntimeError('Publication-gated API accessor did not return preview terms')
    return public


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish',action='store_true',help='Publish exactly one uniquely named archived preview')
    parser.add_argument('--limit',type=int,default=500,help='Number of saved EarnKaro records to inspect (1-5000)')
    args=parser.parse_args()
    if not 1<=args.limit<=5000: parser.error('--limit must be 1-5000')
    from superdeal_local_live_worker import load_env
    load_env()
    backend=connect()
    try:
        candidate=choose_saved_deal(backend.db,limit=args.limit)
        if not candidate:
            print('No eligible saved single-product EarnKaro message with identifiable terms was found. No preview published.')
            return 2
        print('Source EarnKaro record:',candidate['saved']['_id'])
        print('Original product:',candidate['fact']['product']['product_name'])
        print('Coupon codes:',', '.join(candidate['terms']['coupon_codes']) or '(coupon code not explicitly stated)')
        for line in candidate['terms']['source_excerpts']: print('  ',line)
        print('ARCHIVED PREVIEW ONLY: saved price, coupon and eligibility may no longer be valid.')
        if not args.publish:
            print('Read-only inspection complete. Use --publish to display one preview on the frontend.')
            return 0
        offer=publish_replay(backend.db,candidate)
        print('PUBLISHED:',offer['product_name'])
        print('Deal ID:',offer['id'])
        print('Refresh http://localhost:5174/ and search ARCHIVED PREVIEW; open the product title for instructions.')
        return 0
    finally:
        backend.db.client.close()


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print('Replay failed:',type(exc).__name__, str(exc) if type(exc) is RuntimeError else 'Check MongoDB connectivity and the existing replica-set setup.',file=sys.stderr)
        raise SystemExit(1)
