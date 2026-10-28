"""Phase 2: real local MongoDB, no Telegram/EarnKaro/Ollama calls."""
from fixture_link_ids import as_link_ids
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from pymongo import MongoClient
from backend import Backend


@pytest.fixture
def backend():
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017'), serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    name = 'superdeal_test_phase2_' + uuid4().hex
    b = Backend(client[name])
    try:
        b.setup()
        yield b
    finally:
        client.drop_database(name)
        client.close()


def product(url):
    return {'product_name': 'Sony headset '+url.rsplit('/',1)[-1], 'brand': 'Sony', 'ecommerce_platform': 'Amazon',
            'deal_price': 999, 'original_price': 1999, 'discount_percentage': 50,
            'affiliate_urls': [url], 'confidence': 95, 'issues': []}


def configure(b, urls):
    text = '\n'.join(urls)
    b.converter = lambda _: {'response_text': text, 'response_payload': {'data': text}}
    b.llm = lambda _: {'products': [product(u) for u in urls], 'unassigned_urls': [],
                       'message_issues': [], 'analysis_summary': 'fixture'}
    b.llm = as_link_ids(b.llm, lambda: b.converter('fixture')['response_text'])


def test_parallel_ingest_is_idempotent(backend):
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(lambda _: backend.ingest('@parallel', '1', 'sample'), range(16)))
    assert len(set(ids)) == 1
    assert backend.db.raw.count_documents({}) == 1
    assert backend.db.pipeline_status.count_documents({}) == 1


def test_parallel_process_claims_only_once(backend):
    configure(backend, ['https://example.com/a'])
    raw_id = backend.ingest('@parallel', '2', 'sample')
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(backend.process, raw_id) for _ in range(2)]
        results = []
        for f in futures:
            try: results.append(f.result())
            except RuntimeError: results.append('rejected')
    assert sorted(map(str, results)) == ['1', 'rejected']
    assert backend.db.fact_table.count_documents({'raw_id': raw_id}) == 1


def test_no_retry_after_converter_failure(backend):
    raw_id = backend.ingest('@parallel', '3', 'sample')
    backend.converter = lambda _: (_ for _ in ()).throw(RuntimeError('unavailable'))
    assert backend.process(raw_id) == 0
    assert backend.db.pipeline_status.find_one({'raw_id': raw_id})['status'] == 'FAILED'
    with pytest.raises(RuntimeError, match='Only PENDING'):
        backend.process(raw_id)


def test_missing_fact_blocks_entire_published_batch(backend):
    configure(backend, ['https://example.com/a', 'https://example.com/b'])
    raw_id = backend.ingest('@parallel', '4', 'sample')
    assert backend.process(raw_id) == 2
    backend.db.fact_table.delete_one({'raw_id': raw_id, 'offer_index': 1})
    assert backend.published_offers() == []


def test_audit_fallback_file_when_mongo_logging_fails(backend, monkeypatch, tmp_path):
    class FailedCollection:
        def insert_one(self, _): raise OSError('sensitive-provider-response')
    class DBProxy:
        def __getattr__(self, name):
            return FailedCollection() if name == 'pipeline_logs' else getattr(backend_db, name)
    backend_db = backend.db
    backend.db = DBProxy()
    backend.fallback_log_path = tmp_path / 'fallback.jsonl'
    backend.log('sample-id', 'LLM', 'ERROR', 'LLM_FAILURE', error='token=secret')
    payload = backend.fallback_log_path.read_text(encoding='utf-8')
    assert json.loads(payload)['event'] == 'LLM_FAILURE'
    assert 'secret' not in payload and 'sensitive-provider-response' not in payload


def test_failure_status_write_does_not_suppress_fallback_logging(backend, tmp_path):
    class Broken:
        def update_one(self, *args, **kwargs): raise OSError('db down')
        def insert_one(self, *args, **kwargs): raise OSError('db down')
    class DBProxy:
        def __getattr__(self, name):
            return Broken() if name in ('pipeline_status', 'pipeline_logs') else getattr(original, name)
    original = backend.db
    backend.db = DBProxy()
    backend.fallback_log_path = tmp_path / 'fallback.jsonl'
    backend._fail('id', 'LLM', ValueError('secret'))
    assert backend.fallback_log_path.exists()


def test_uncommitted_facts_are_not_visible(backend):
    raw_id = backend.ingest('@parallel', '5', 'sample')
    backend.db.fact_table.insert_one({'raw_id': raw_id, 'offer_index': 0, 'publication_id': 'pending',
                                      'product': product('https://example.com/a')})
    assert backend.published_offers() == []


def test_interrupted_jobs_do_not_resume(backend):
    raw_id = backend.ingest('@parallel', '6', 'sample')
    backend.db.pipeline_status.update_one({'raw_id': raw_id}, {'$set': {'status': 'PROCESSING'}})
    assert backend.fail_interrupted_jobs() == 1
    with pytest.raises(RuntimeError, match='Only PENDING'):
        backend.process(raw_id)
