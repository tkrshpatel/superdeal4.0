"""Hardening tests against an isolated, disposable local MongoDB database."""
from fixture_link_ids import as_link_ids
import os
from uuid import uuid4
import pytest
from pymongo import MongoClient
from backend import Backend

@pytest.fixture
def backend():
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017'), serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    name = 'superdeal_test_hardening_' + uuid4().hex
    instance = Backend(client[name])
    try:
        instance.setup()
        yield instance
    finally:
        client.drop_database(name)
        client.close()

def product(url):
    return {'product_name':'Sony headset '+url.rsplit('/',1)[-1],'brand':'Sony','ecommerce_platform':'Amazon',
            'deal_price':999,'original_price':1999,'discount_percentage':50,
            'affiliate_urls':[url],'confidence':95,'issues':[]}

def configure(backend, *products):
    content = '\n'.join(p['affiliate_urls'][0] for p in products)
    backend.converter = lambda _: {'response_text':content, 'response_payload':{'data':content}}
    backend.llm = lambda _: {'products':list(products), 'unassigned_urls':[], 'message_issues':[], 'analysis_summary':'test'}
    backend.llm = as_link_ids(backend.llm, lambda: backend.converter('fixture')['response_text'])

def test_interrupted_processing_becomes_failed_without_retry(backend):
    raw_id = backend.ingest('@fixture', '1', 'sample')
    backend.db.pipeline_status.update_one({'raw_id':raw_id},{'$set':{'status':'PROCESSING','current_stage':'LLM'}})
    assert backend.fail_interrupted_jobs() == 1
    assert backend.fail_interrupted_jobs() == 0
    assert backend.db.pipeline_status.find_one({'raw_id':raw_id})['status'] == 'FAILED'
    assert backend.db.pipeline_logs.count_documents({'raw_id':raw_id,'event':'INTERRUPTED_JOB_FAILED'}) == 1
    with pytest.raises(RuntimeError, match='Only PENDING'):
        backend.process(raw_id)

def test_missing_fact_in_published_batch_hides_entire_batch(backend):
    configure(backend, product('https://example.com/a'), product('https://example.com/b'))
    raw_id = backend.ingest('@fixture','2','sample')
    assert backend.process(raw_id) == 2
    assert len(backend.published_offers()) == 2
    backend.db.fact_table.delete_one({'raw_id':raw_id,'offer_index':1})
    assert backend.published_offers() == []

def test_duplicate_offer_index_in_published_batch_hides_batch(backend):
    configure(backend, product('https://example.com/a'), product('https://example.com/b'))
    raw_id = backend.ingest('@fixture','3','sample')
    assert backend.process(raw_id) == 2
    backend.db.fact_table.update_one({'raw_id':raw_id,'offer_index':1},{'$set':{'offer_index':2}})
    assert backend.published_offers() == []

def test_staged_facts_not_visible_and_interrupted_job_fails(backend):
    raw_id = backend.ingest('@fixture','4','sample')
    backend.db.pipeline_status.update_one({'raw_id':raw_id},{'$set':{'status':'PROCESSING'}})
    backend.db.fact_table.insert_one({'raw_id':raw_id,'offer_index':0,'publication_id':'incomplete',
                                      'product':product('https://example.com/a')})
    assert backend.published_offers() == []
    assert backend.fail_interrupted_jobs() == 1
    assert backend.published_offers() == []

def test_failed_job_remains_failed_after_duplicate_ingest(backend):
    raw_id = backend.ingest('@fixture','5','sample')
    backend.db.pipeline_status.update_one({'raw_id':raw_id},{'$set':{'status':'FAILED'}})
    assert backend.ingest('@fixture','5','sample') == raw_id
    assert backend.db.pipeline_status.find_one({'raw_id':raw_id})['status'] == 'FAILED'

def test_publication_commit_status_guard(backend):
    configure(backend, product('https://example.com/a'))
    raw_id = backend.ingest('@fixture','6','sample')
    # Simulates a concurrent operator setting a terminal state before publication.
    original = backend.db.pipeline_status
    class Guard:
        def __getattr__(self, name):
            return getattr(original, name)
        def update_one(self, query, update, **kwargs):
            if query.get('status') == 'PROCESSING' and update.get('$set',{}).get('status') == 'PUBLISHED':
                original.update_one({'raw_id':raw_id},{'$set':{'status':'FAILED'}})
            return original.update_one(query,update,**kwargs)
    # pymongo collection attributes cannot be reassigned; replace DB proxy.
    real_db = backend.db
    class Proxy:
        def __getattr__(self, name):
            return Guard() if name == 'pipeline_status' else getattr(real_db,name)
    backend.db = Proxy()
    assert backend.process(raw_id) == 0
    assert backend.published_offers() == []
