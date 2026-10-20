"""Isolated SuperDeal MongoDB backend. No Telegram listener or automatic scheduler."""
from __future__ import annotations
import json
import sys
import logging
import os
import re
import traceback
from datetime import datetime, timezone
from uuid import uuid4

import requests
from pymongo import MongoClient, ASCENDING
from pymongo.errors import PyMongoError

LOG = logging.getLogger('superdeal.mongo')
URL_RE = re.compile(r'https?://[^\s<>"\']+')
STAGES = {'TELEGRAM', 'EARNKARO', 'LLM', 'VALIDATION', 'PUBLICATION'}
FIELDS = {'product_name', 'brand', 'ecommerce_platform', 'deal_price', 'original_price', 'discount_percentage', 'affiliate_urls', 'confidence', 'issues'}


def now():
    return datetime.now(timezone.utc)


def urls(text):
    return set(u.rstrip('.,;!?)\\]}>') for u in URL_RE.findall(text or ''))


class Backend:
    def __init__(self, db, *, llm=None, converter=None):
        self.db = db
        self.llm = llm or self._ollama
        self.converter = converter or self._earnkaro

    def setup(self):
        self.db.raw.create_index([('channel', ASCENDING), ('message_id', ASCENDING)], unique=True)
        self.db.ek_raw.create_index('raw_id', unique=True)
        self.db.pipeline_status.create_index('raw_id', unique=True)
        self.db.pipeline_logs.create_index([('raw_id', ASCENDING), ('timestamp', ASCENDING)])
        self.db.fact_table.create_index([('raw_id', ASCENDING), ('offer_index', ASCENDING)], unique=True)
        self.db.fact_table.create_index('publication_id')

    def log(self, raw_id, stage, severity, event, *, error=None, details=None):
        item = {'raw_id': raw_id, 'stage': stage, 'severity': severity, 'event': event,
                'timestamp': now(), 'error': error, 'details': details or {}}
        try:
            self.db.pipeline_logs.insert_one(item)
        except Exception:
            # stderr is a fallback when MongoDB audit logging is unavailable.
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
        result = self.db.raw.update_one({'channel': channel, 'message_id': str(message_id)},
                                        {'$setOnInsert': doc}, upsert=True)
        raw = self.db.raw.find_one({'channel': channel, 'message_id': str(message_id)})
        self.db.pipeline_status.update_one({'raw_id': raw['_id']}, {'$setOnInsert': {
            'raw_id': raw['_id'], 'status': 'PENDING', 'current_stage': 'TELEGRAM',
            'products_extracted': 0, 'products_published': 0,
            'created_at': now(), 'updated_at': now()}}, upsert=True)
        if result.upserted_id is not None:
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
        self.db.pipeline_status.update_one({'raw_id': raw_id, 'status': {'$nin': ['PUBLISHED', 'FAILED']}},
            {'$set': {'status': 'FAILED', 'current_stage': stage, 'error_message': str(exc)[:2000], 'updated_at': now()}})
        self.log(raw_id, stage, 'ERROR', 'STAGE_FAILED', error=str(exc),
                 details={'traceback': traceback.format_exc()[-8000:]})

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
        status = self.db.pipeline_status.find_one({'raw_id': raw_id})
        if not status or status['status'] != 'PENDING':
            raise RuntimeError('Only PENDING messages may run; no retries')
        stage = 'EARNKARO'
        try:
            raw = self.db.raw.find_one({'_id': raw_id})
            if raw is None:
                raise ValueError('Missing raw message')
            self._transition(raw_id, stage)
            converted = self.converter(raw['text'])
            if not isinstance(converted, dict) or not isinstance(converted.get('response_text'), str) or not converted['response_text'].strip():
                raise ValueError('Invalid EarnKaro conversion response')
            self.db.ek_raw.insert_one({'raw_id': raw_id, **converted, 'created_at': now()})
            self.log(raw_id, stage, 'INFO', 'CONVERTED')
            stage = 'LLM'
            self._transition(raw_id, stage)
            llm_response = self.llm(converted['response_text'])
            stage = 'VALIDATION'
            self._transition(raw_id, stage)
            parsed = self.validate(llm_response, converted['response_text'])
            self.db.pipeline_status.update_one({'raw_id': raw_id}, {'$set': {'products_extracted': len(parsed['products']), 'updated_at': now()}})
            self.log(raw_id, stage, 'INFO', 'VALIDATED', details={'products': len(parsed['products'])})
            stage = 'PUBLICATION'
            self._transition(raw_id, stage)
            # Visibility is controlled exclusively by status=PUBLISHED and publication_id.
            # A crash before status update leaves all staged facts invisible.
            publication_id = str(uuid4())
            for idx, p in enumerate(parsed['products']):
                self.db.fact_table.insert_one({'raw_id': raw_id, 'offer_index': idx, 'publication_id': publication_id,
                    'product': p, 'llm_response': llm_response, 'model': os.getenv('OLLAMA_MODEL', 'mistral:instruct'),
                    'created_at': now()})
            commit = self.db.pipeline_status.update_one({'raw_id': raw_id, 'status': 'PROCESSING'}, {'$set': {
                'status': 'PUBLISHED', 'current_stage': 'PUBLICATION', 'publication_id': publication_id,
                'products_published': len(parsed['products']), 'published_at': now(), 'updated_at': now()}})
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
                LOG.error('PUBLICATION_INTEGRITY_FAILED raw_id=%s', raw_id)
                continue
            for fact in facts:
                results.append({'id': str(fact['_id']), **fact['product']})
                if len(results) >= limit:
                    return results
        return results


def connect():
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017'), serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    return Backend(client[os.getenv('MONGODB_DATABASE', 'superdeal')])
