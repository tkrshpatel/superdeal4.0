"""Isolated SuperDeal MongoDB backend. No Telegram listener or automatic scheduler."""
from __future__ import annotations
import json
import pathlib
import threading
import sys
import logging
import os
import re
import traceback
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import requests
from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError, DuplicateKeyError

LOG = logging.getLogger('superdeal.mongo')
URL_RE = re.compile(r'https?://[^\s<>"\']+')
STAGES = {'TELEGRAM', 'EARNKARO', 'LLM', 'VALIDATION', 'IMAGE_ENRICHMENT', 'PRODUCT_RESEARCH', 'PUBLICATION'}
FIELDS = {'product_name', 'brand', 'ecommerce_platform', 'deal_price', 'original_price', 'discount_percentage', 'affiliate_urls', 'confidence', 'issues'}

# Safe, fixed validation labels for diagnostics; never log raw model text or URLs.
VALIDATION_REASONS = frozenset({
    'Invalid LLM root schema',
    'No publishable products',
    'Invalid LLM metadata',
    'Unassigned URLs block all-or-nothing publication',
    'Invalid product schema',
    'Product name required for publication',
    'Product affiliate URLs required',
    'Invalid confidence/issues',
    'Invalid price or discount',
    'Invalid brand/platform',
    'Missing, invented, or duplicated affiliate URLs',
})



def now():
    return datetime.now(timezone.utc)


def urls(text):
    return set(u.rstrip('.,;!?)\\]}>') for u in URL_RE.findall(text or ''))


class Backend:
    def __init__(self, db, *, llm=None, converter=None, image_scraper=None):
        self.db = db
        self.llm = llm or self._ollama
        self.converter = converter or self._earnkaro
        self.image_scraper = image_scraper
        self.fallback_log_path = pathlib.Path(os.getenv('SUPERDEAL_FALLBACK_LOG', 'data/superdeal_fallback_errors.jsonl'))
        self._fallback_lock = threading.Lock()

    def setup(self):
        self.db.raw.create_index([('channel', ASCENDING), ('message_id', ASCENDING)], unique=True)
        self.db.ek_raw.create_index('raw_id', unique=True)
        self.db.playwright_raw.create_index([('raw_id', ASCENDING), ('affiliate_url', ASCENDING)], unique=True)
        self.db.pipeline_status.create_index('raw_id', unique=True)
        self.db.pipeline_logs.create_index([('raw_id', ASCENDING), ('timestamp', ASCENDING)])
        self.db.fact_table.create_index([('raw_id', ASCENDING), ('offer_index', ASCENDING)], unique=True)
        self.db.fact_table.create_index('publication_id')
        self.db.pipeline_status.create_index('status')
        self.db.pipeline_status.create_index([('status', ASCENDING), ('published_at', -1), ('_id', -1)])
        self.db.deal_clicks.create_index([('deal_id', ASCENDING), ('clicked_at', -1)])

    def log(self, raw_id, stage, severity, event, *, error=None, details=None):
        item = {'raw_id': raw_id, 'stage': stage, 'severity': severity, 'event': event,
                'timestamp': now(), 'error': error, 'details': details or {}}
        try:
            self.db.pipeline_logs.insert_one(item)
        except Exception:
            # Persist a scrubbed, local audit fallback if MongoDB logging fails.
            # Never include raw messages, tokens, HTTP response bodies or tracebacks.
            fallback = {'timestamp': now().isoformat(), 'raw_id': str(raw_id),
                        'stage': stage, 'severity': severity, 'event': event,
                        'audit_write_failed': True}
            try:
                with self._fallback_lock:
                    self.fallback_log_path.parent.mkdir(parents=True, exist_ok=True)
                    with self.fallback_log_path.open('a', encoding='utf-8') as handle:
                        handle.write(json.dumps(fallback) + '\n')
            except Exception:
                LOG.exception('AUDIT_FALLBACK_WRITE_FAILED')
            LOG.exception('AUDIT_LOG_WRITE_FAILED stage=%s event=%s raw_id=%s', stage, event, raw_id)
            print(f'AUDIT_LOG_WRITE_FAILED stage={stage} event={event} raw_id={raw_id}', file=sys.stderr)
        if severity in {'ERROR', 'CRITICAL'}:
            LOG.error('pipeline failure stage=%s event=%s raw_id=%s error=%s', stage, event, raw_id, error)
        else:
            LOG.info('pipeline event stage=%s event=%s raw_id=%s', stage, event, raw_id)

    def ingest(self, channel, message_id, text, observed_at=None):
        if not channel or not str(message_id) or not isinstance(text, str) or not text.strip():
            raise ValueError('channel, message_id and nonempty text required')
        doc = {'channel': channel, 'message_id': str(message_id), 'text': text,
               'observed_at': observed_at or now(), 'created_at': now()}
        # Idempotent insertion. Existing records never restart a failed/published job.
        try:
            result = self.db.raw.update_one({'channel': channel, 'message_id': str(message_id)},
                                            {'$setOnInsert': doc}, upsert=True)
        except DuplicateKeyError:
            # Concurrent duplicate insert; unique index is authoritative.
            result = None
        raw = self.db.raw.find_one({'channel': channel, 'message_id': str(message_id)})
        try:
            self.db.pipeline_status.update_one({'raw_id': raw['_id']}, {'$setOnInsert': {
                'raw_id': raw['_id'], 'status': 'PENDING', 'current_stage': 'TELEGRAM',
                'products_extracted': 0, 'products_published': 0,
                'created_at': now(), 'updated_at': now()}}, upsert=True)
        except DuplicateKeyError:
            # Another worker initialized this status concurrently.
            pass
        if result is not None and result.upserted_id is not None:
            self.log(raw['_id'], 'TELEGRAM', 'INFO', 'INGESTED')
        return raw['_id']

    def _transition(self, raw_id, stage):
        result = self.db.pipeline_status.update_one(
            {'raw_id': raw_id, 'status': {'$in': ['PENDING', 'PROCESSING']}},
            {'$set': {'status': 'PROCESSING', 'current_stage': stage, 'updated_at': now()}})
        if result.matched_count != 1:
            raise RuntimeError('Job is terminal or missing; no retry permitted')
        self.log(raw_id, stage, 'INFO', 'STAGE_STARTED')

    def _fail(self, raw_id, stage, exc):
        # Failure status and audit logging must be attempted independently.
        try:
            self.db.pipeline_status.update_one({'raw_id': raw_id, 'status': {'$nin': ['PUBLISHED', 'FAILED']}},
                {'$set': {'status': 'FAILED', 'current_stage': stage,
                          'error_message': type(exc).__name__, 'updated_at': now()}})
        except Exception:
            LOG.exception('FAILED_TO_MARK_JOB_FAILED raw_id=%s', raw_id)
        reason = str(exc) if stage == 'VALIDATION' and type(exc) is ValueError and str(exc) in VALIDATION_REASONS else None
        self.log(raw_id, stage, 'ERROR', 'STAGE_FAILED', error=type(exc).__name__,
                 details={'reason': reason} if reason else {})
        if reason:
            print(f'VALIDATION_FAILED raw_id={raw_id} reason={reason}', file=sys.stderr, flush=True)

    @staticmethod
    def _earnkaro(text):
        key = os.environ['API_KEY_EARNKARO']
        resp = requests.post('https://ekaro-api.affiliaters.in/api/converter/public',
            headers={'Authorization': 'Bearer ' + key},
            json={'deal': text, 'convert_option': 'convert_only'}, timeout=25)
        resp.raise_for_status()
        body = resp.json()
        converted = body.get('data')
        if not isinstance(converted, str) or not converted.strip() or 'we could not find' in converted.lower():
            raise ValueError('EarnKaro did not return a usable converted message')
        return {'response_text': converted, 'response_payload': body}

    @staticmethod
    def _ollama(text):
        from prompt import PROMPT
        resp = requests.post(os.getenv('OLLAMA_URL', 'http://127.0.0.1:11434/api/chat'),
            json={'model': os.getenv('OLLAMA_MODEL', 'mistral:instruct'), 'stream': False,
                  'format': 'json', 'options': {'temperature': 0},
                  'messages': [{'role': 'system', 'content': PROMPT}, {'role': 'user', 'content': text}]},
            timeout=240)
        resp.raise_for_status()
        return resp.json()['message']['content']

    @staticmethod
    def validate(response, source_text):
        parsed = json.loads(response) if isinstance(response, str) else response
        # Mistral may omit explanatory prose despite returning valid structured
        # deals. Restore only this non-factual metadata field; never repair
        # URLs, product records, prices, or unassigned links.
        if isinstance(parsed, dict) and 'analysis_summary' not in parsed:
            parsed = {**parsed, 'analysis_summary': ''}
        if not isinstance(parsed, dict) or set(parsed) != {'products', 'unassigned_urls', 'message_issues', 'analysis_summary'}:
            raise ValueError('Invalid LLM root schema')
        products = parsed['products']
        if not isinstance(products, list) or not products:
            raise ValueError('No publishable products')
        if not isinstance(parsed['unassigned_urls'], list) or not isinstance(parsed['message_issues'], list) or not isinstance(parsed['analysis_summary'], str):
            raise ValueError('Invalid LLM metadata')
        if parsed['unassigned_urls']:
            raise ValueError('Unassigned URLs block all-or-nothing publication')
        collected = []
        for p in products:
            if not isinstance(p, dict) or set(p) != FIELDS:
                raise ValueError('Invalid product schema')
            if not isinstance(p['product_name'], str) or not p['product_name'].strip():
                raise ValueError('Product name required for publication')
            if not isinstance(p['affiliate_urls'], list) or not p['affiliate_urls'] or not all(isinstance(u, str) for u in p['affiliate_urls']):
                raise ValueError('Product affiliate URLs required')
            if type(p['confidence']) is not int or not 0 <= p['confidence'] <= 100 or not isinstance(p['issues'], list):
                raise ValueError('Invalid confidence/issues')
            if any(v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0) for v in (p['deal_price'], p['original_price'], p['discount_percentage'])):
                raise ValueError('Invalid price or discount')
            if any(v is not None and not isinstance(v, str) for v in (p['brand'], p['ecommerce_platform'])):
                raise ValueError('Invalid brand/platform')
            collected.extend(p['affiliate_urls'])
        if len(collected) != len(set(collected)) or set(collected) != urls(source_text):
            raise ValueError('Missing, invented, or duplicated affiliate URLs')
        return parsed

    def fail_interrupted_jobs(self):
        """Explicit operator recovery: mark interrupted jobs FAILED, never retry.

        Run during maintenance/startup with processing workers stopped.
        """
        ids = [d['raw_id'] for d in self.db.pipeline_status.find(
            {'status': 'PROCESSING'}, {'raw_id': 1})]
        failed = 0
        for raw_id in ids:
            result = self.db.pipeline_status.update_one(
                {'raw_id': raw_id, 'status': 'PROCESSING'},
                {'$set': {'status': 'FAILED', 'error_message': 'Interrupted processing; manual review required',
                          'updated_at': now()}})
            if result.modified_count:
                failed += 1
                self.log(raw_id, 'RECOVERY', 'ERROR', 'INTERRUPTED_JOB_FAILED',
                         error='Interrupted processing; no automatic retry')
        return failed

    def process(self, raw_id):
        # Atomic claim prevents two workers from processing the same message.
        claimed = self.db.pipeline_status.update_one(
            {'raw_id': raw_id, 'status': 'PENDING'},
            {'$set': {'status': 'PROCESSING', 'current_stage': 'EARNKARO', 'updated_at': now()}})
        if claimed.modified_count != 1:
            raise RuntimeError('Only PENDING messages may run; no retries')
        stage = 'EARNKARO'
        try:
            raw = self.db.raw.find_one({'_id': raw_id})
            if raw is None:
                raise ValueError('Missing raw message')
            self.log(raw_id, stage, 'INFO', 'STAGE_STARTED')
            converted = self.converter(raw['text'])
            if not isinstance(converted, dict) or not isinstance(converted.get('response_text'), str) or not converted['response_text'].strip():
                raise ValueError('Invalid EarnKaro conversion response')
            self.db.ek_raw.insert_one({'raw_id': raw_id, 'response_text': converted['response_text'],
                                       'response_payload': converted.get('response_payload'), 'created_at': now()})
            self.log(raw_id, stage, 'INFO', 'CONVERTED')
            # Experiment: collect merchant page evidence before LLM, without
            # rewriting any EarnKaro URL or changing the default pipeline.
            research = None
            llm_input = converted['response_text']
            if os.getenv('SUPERDEAL_PRE_LLM_RESEARCH') == '1':
                stage = 'PRODUCT_RESEARCH'
                self._transition(raw_id, stage)
                from pre_llm_research import (research_message, llm_evidence,
                                              persist_research, load_research)
                try:
                    research = research_message(converted['response_text'])
                except Exception as exc:
                    self.log(raw_id, stage, 'ERROR', 'RESEARCH_FAILED', error=type(exc).__name__)
                    # A failed research run is retained as diagnostics for every
                    # EarnKaro link, rather than silently losing source records.
                    research = {link: {
                        'status': 'RESEARCH_FAILED', 'product_name': None,
                        'description': None, 'brand': None, 'image_url': None,
                        'price': None, 'mrp': None, 'price_source': None,
                        'mrp_source': None,
                    } for link in urls(converted['response_text'])}
                persist_research(self.db.playwright_raw, raw_id, converted['response_text'], research)
                # Mistral must consume the MongoDB snapshot, not a separate
                # in-memory version of the scraped information.
                research = load_research(self.db.playwright_raw, raw_id, converted['response_text'])
                self.log(raw_id, stage, 'INFO', 'RESEARCH_STORED', details={'links': len(research)})
                llm_input = llm_evidence(converted['response_text'], research)
            stage = 'LLM'
            self._transition(raw_id, stage)
            llm_response = self.llm(llm_input)
            stage = 'VALIDATION'
            self._transition(raw_id, stage)
            parsed = self.validate(llm_response, converted['response_text'])
            if research is not None:
                from pre_llm_research import fill_missing_mrp
                fill_missing_mrp(parsed['products'], research)
            self.db.pipeline_status.update_one({'raw_id': raw_id}, {'$set': {'products_extracted': len(parsed['products']), 'updated_at': now()}})
            self.log(raw_id, stage, 'INFO', 'VALIDATED', details={'products': len(parsed['products'])})
            # Image enrichment is synchronous and completes before publication.
            # Missing/blocked images use the local placeholder; they never trigger
            # a separate background job or retry a failed message.
            stage = 'IMAGE_ENRICHMENT'
            self._transition(raw_id, stage)
            if research is not None:
                from pre_llm_research import research_images
                images = research_images(parsed['products'], research)
            else:
                from image_enrichment import enrich_products
                images = enrich_products(raw['text'], parsed['products'], scraper=self.image_scraper)
            if len(images) != len(parsed['products']):
                raise RuntimeError('Image enrichment returned incomplete product results')
            self.log(raw_id, stage, 'INFO', 'ENRICHED', details={
                'found': sum(item['status'] == 'FOUND' for item in images),
                'placeholder': sum(item['status'] == 'PLACEHOLDER' for item in images),
            })
            stage = 'PUBLICATION'
            self._transition(raw_id, stage)
            # Transactionally commit all product facts and the publication gate.
            # MongoDB requires a replica set (including a single-node replica set).
            publication_id = str(uuid4())
            client = self.db.client
            with client.start_session() as session:
                with session.start_transaction():
                    for idx, p in enumerate(parsed['products']):
                        self.db.fact_table.insert_one({
                            'raw_id': raw_id, 'offer_index': idx,
                            'publication_id': publication_id, 'product': p,
                            'image_enrichment': images[idx],
                            'llm_response': llm_response,
                            'model': os.getenv('OLLAMA_MODEL', 'mistral:instruct'),
                            'created_at': now(),
                        }, session=session)
                    commit = self.db.pipeline_status.update_one(
                        {'raw_id': raw_id, 'status': 'PROCESSING'},
                        {'$set': {
                            'status': 'PUBLISHED', 'current_stage': 'PUBLICATION',
                            'publication_id': publication_id,
                            'products_published': len(parsed['products']),
                            'published_at': now(), 'updated_at': now(),
                        }}, session=session)
                    if commit.modified_count != 1:
                        raise RuntimeError('Publication status commit failed')
            self.log(raw_id, stage, 'INFO', 'PUBLISHED', details={'products': len(parsed['products'])})
            return len(parsed['products'])
        except Exception as exc:
            self._fail(raw_id, stage, exc)
            return 0

    def published_offers(self, limit=100):
        """Publication gate for web/mobile: never query fact_table directly."""
        statuses = self.db.pipeline_status.find({'status': 'PUBLISHED'}, {'raw_id': 1, 'publication_id': 1, 'products_published': 1})
        pairs = [(s['raw_id'], s.get('publication_id'), s.get('products_published')) for s in statuses if s.get('publication_id')]
        results = []
        for raw_id, pub_id, expected in pairs:
            if not isinstance(expected, int) or expected < 1:
                continue
            facts = list(self.db.fact_table.find({'raw_id': raw_id, 'publication_id': pub_id}).sort('offer_index', 1))
            if len(facts) != expected or [f.get('offer_index') for f in facts] != list(range(expected)):
                self.log(raw_id, 'PUBLICATION', 'ERROR', 'PUBLICATION_INTEGRITY_FAILED')
                continue
            for fact in facts:
                results.append({'id': str(fact['_id']), **fact['product'], 'image_url': (fact.get('image_enrichment') or {}).get('image_url'), 'enrichment_status': (fact.get('image_enrichment') or {}).get('status')})
                if len(results) >= limit:
                    return results
        return results

    def _published_pipeline(self, *, offset=0, limit=20, fact_id=None):
        """Publication-gated, DB-paginated facts. Deterministic newest-first order.

        Join each fact with its committed publication status, then paginate in MongoDB.
        The transaction guarantees that committed PUBLISHED batches are complete.
        """
        pipeline = []
        if fact_id is not None:
            pipeline.append({'$match': {'_id': fact_id}})
        pipeline += [
            {'$lookup': {
                'from': 'pipeline_status', 'localField': 'raw_id',
                'foreignField': 'raw_id', 'as': '_publication',
            }},
            {'$unwind': '$_publication'},
            {'$match': {'_publication.status': 'PUBLISHED',
                        '$expr': {'$eq': ['$publication_id', '$_publication.publication_id']}}},
            {'$sort': {'_publication.published_at': -1, 'raw_id': -1,
                       'offer_index': 1, '_id': -1}},
        ]
        if offset:
            pipeline.append({'$skip': offset})
        pipeline.append({'$limit': limit})
        pipeline.append({'$project': {'product': 1, 'image_enrichment': 1}})
        return pipeline

    def published_page(self, *, limit=20, offset=0):
        if not 1 <= limit <= 100 or not 0 <= offset <= 10000:
            raise ValueError('Invalid pagination')
        docs = list(self.db.fact_table.aggregate(
            self._published_pipeline(offset=offset, limit=limit + 1)))
        items = [{'id': str(doc['_id']), **doc['product'], 'image_url': (doc.get('image_enrichment') or {}).get('image_url'), 'enrichment_status': (doc.get('image_enrichment') or {}).get('status')} for doc in docs[:limit]]
        return {'items': items, 'limit': limit, 'offset': offset,
                'has_more': len(docs) > limit}

    def legacy_search(self, *, limit=50, q=None, merchant=None, min_price=None, max_price=None, sort='newest'):
        """Publication-gated server-side legacy search; unknown metadata stays unavailable."""
        if sort not in ('newest', 'price_asc', 'price_desc', 'popular'):
            raise ValueError('Invalid sort')
        if min_price is not None and (min_price < 0 or (max_price is not None and min_price > max_price)):
            raise ValueError('Invalid price range')
        if max_price is not None and max_price < 0:
            raise ValueError('Invalid price range')
        pipeline = self._published_pipeline(limit=100000)
        # Apply filters before sorting and limiting; never scan/limit results in Python.
        pipeline = [x for x in pipeline if '$limit' not in x and '$sort' not in x and '$project' not in x]
        criteria = []
        if q:
            escaped = re.escape(q[:120])
            criteria.append({'$or': [{'product.product_name': {'$regex': escaped, '$options': 'i'}},
                                     {'product.brand': {'$regex': escaped, '$options': 'i'}},
                                     {'product.ecommerce_platform': {'$regex': escaped, '$options': 'i'}}]})
        if merchant:
            criteria.append({'product.ecommerce_platform': {'$regex': '^' + re.escape(merchant[:120]) + '$', '$options': 'i'}})
        price = {}
        if min_price is not None: price['$gte'] = min_price
        if max_price is not None: price['$lte'] = max_price
        if price: criteria.append({'product.deal_price': price})
        if criteria: pipeline.append({'$match': {'$and': criteria}})
        if sort == 'popular':
            # Rank by observed /go clicks in the last 24 hours only.
            # Do not claim this represents unobserved or historical traffic.
            cutoff = now() - timedelta(hours=24)
            pipeline.extend([
                {'$addFields': {'_deal_id_string': {'$toString': '$_id'}}},
                {'$lookup': {
                    'from': 'deal_clicks',
                    'let': {'deal_id': '$_deal_id_string'},
                    'pipeline': [
                        {'$match': {'$expr': {'$and': [
                            {'$eq': ['$deal_id', '$$deal_id']},
                            {'$gte': ['$clicked_at', cutoff]},
                        ]}}},
                        {'$count': 'count'},
                    ],
                    'as': '_clicks',
                }},
                {'$addFields': {'_click_count': {'$ifNull': [{'$arrayElemAt': ['$_clicks.count', 0]}, 0]}}},
                {'$sort': {'_click_count': -1, '_publication.published_at': -1, '_id': -1}},
                {'$limit': limit + 1},
                {'$project': {'product': 1, 'image_enrichment': 1}},
            ])
            docs = list(self.db.fact_table.aggregate(pipeline))
            return {'items': [{'id': str(d['_id']), **d['product'], 'image_url': (d.get('image_enrichment') or {}).get('image_url'), 'enrichment_status': (d.get('image_enrichment') or {}).get('status')} for d in docs[:limit]],
                    'has_more': len(docs) > limit}
        order = {'newest': {'_publication.published_at': -1, '_id': -1},
                 'price_asc': {'product.deal_price': 1, '_id': -1},
                 'price_desc': {'product.deal_price': -1, '_id': -1}}[sort]
        pipeline.extend([{'$sort': order}, {'$limit': limit + 1}, {'$project': {'product': 1, 'image_enrichment': 1}}])
        docs = list(self.db.fact_table.aggregate(pipeline))
        return {'items': [{'id': str(d['_id']), **d['product'], 'image_url': (d.get('image_enrichment') or {}).get('image_url'), 'enrichment_status': (d.get('image_enrichment') or {}).get('status')} for d in docs[:limit]], 'has_more': len(docs) > limit}

    def public_metadata(self, deal_id):
        """Derived only from committed publication and observed click records.

        Publication time is NOT the time a merchant's price was verified.
        """
        from bson import ObjectId
        from bson.errors import InvalidId
        try:
            oid = ObjectId(deal_id)
        except (InvalidId, TypeError):
            return None
        fact = self.db.fact_table.find_one({'_id': oid}, {'raw_id': 1, 'publication_id': 1})
        if not fact:
            return None
        status = self.db.pipeline_status.find_one({
            'raw_id': fact['raw_id'], 'status': 'PUBLISHED',
            'publication_id': fact.get('publication_id')}, {'published_at': 1})
        if not status:
            return None
        published_at = status.get('published_at')

        # PyMongo returns naive UTC datetimes by default.
        if published_at is not None and published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)

        cutoff = now() - timedelta(hours=24)
        clicks = self.db.deal_clicks.count_documents({'deal_id': deal_id, 'clicked_at': {'$gte': cutoff}})
        return {'published_at': published_at, 'click_count': clicks,
                'hot': clicks >= 5, 'fresh_window_hours': 24,
                'fresh': bool(published_at and published_at >= cutoff)}

    def affiliate_destination(self, deal_id):
        """Return an exact, validated published affiliate URL; never rewrite it."""
        from urllib.parse import urlsplit
        item = self.published_offer_by_id(deal_id)
        if not item: return None
        for url in item.get('affiliate_urls') or []:
            if not isinstance(url, str): continue
            parsed = urlsplit(url)
            if parsed.scheme in ('https', 'http') and parsed.hostname and not parsed.username and not parsed.password and not any(c in url for c in '\r\n'):
                return url
        return None

    def record_affiliate_click(self, deal_id):
        """Click telemetry only; must not block an otherwise valid redirect."""
        try:
            self.db.deal_clicks.insert_one({'deal_id': deal_id, 'clicked_at': now()})
        except Exception:
            LOG.exception('Affiliate click telemetry failed')

    def published_offer_by_id(self, deal_id):
        from bson import ObjectId
        from bson.errors import InvalidId
        try:
            oid = ObjectId(deal_id)
        except (InvalidId, TypeError):
            return None
        docs = list(self.db.fact_table.aggregate(self._published_pipeline(limit=1, fact_id=oid)))
        return {'id': str(docs[0]['_id']), **docs[0]['product'], 'image_url': (docs[0].get('image_enrichment') or {}).get('image_url'), 'enrichment_status': (docs[0].get('image_enrichment') or {}).get('status')} if docs else None


def connect():
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017'), serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    return Backend(client[os.getenv('MONGODB_DATABASE', 'superdeal')])
