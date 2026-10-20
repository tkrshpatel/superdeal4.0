"""Real MongoDB replica-set transaction tests; no external provider calls."""
from uuid import uuid4
import os
import pytest
from pymongo import MongoClient
from pymongo.collection import Collection
# Load the backend shipped beside this test, never a same-named module
# from the repository root or an earlier pytest import.
import importlib.util
from pathlib import Path
_spec = importlib.util.spec_from_file_location('superdeal_phase3_transaction_backend', Path(__file__).resolve().parent / 'backend.py')
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
Backend = _module.Backend

URLS = ['https://example.com/first', 'https://example.com/second']

def product(url):
    return {'product_name': 'Test item', 'brand': None, 'ecommerce_platform': None,
            'deal_price': 100, 'original_price': 200, 'discount_percentage': 50,
            'affiliate_urls': [url], 'confidence': 95, 'issues': []}

@pytest.fixture
def backend():
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/?replicaSet=rs0'), serverSelectionTimeoutMS=10000)
    hello = client.admin.command('hello')
    if not hello.get('setName'):
        pytest.skip('MongoDB replica set required for transaction tests')
    name = 'superdeal_test_tx_' + uuid4().hex
    b = Backend(client[name])
    b.setup()
    text = '\n'.join(URLS)
    b.converter = lambda _: {'response_text': text, 'response_payload': {'data': text}}
    b.llm = lambda _: {'products': [product(u) for u in URLS], 'unassigned_urls': [],
                       'message_issues': [], 'analysis_summary': 'test'}
    try:
        yield b
    finally:
        client.drop_database(name)
        client.close()

def test_two_products_and_status_commit_together(backend):
    raw_id = backend.ingest('@test', '1', 'synthetic')
    assert backend.process(raw_id) == 2
    assert backend.db.pipeline_status.find_one({'raw_id': raw_id})['status'] == 'PUBLISHED'
    assert backend.db.fact_table.count_documents({'raw_id': raw_id}) == 2
    assert len(backend.published_offers()) == 2

def test_second_insert_failure_rolls_back_first_and_status(backend, monkeypatch):
    raw_id = backend.ingest('@test', '2', 'synthetic')
    original = Collection.insert_one
    calls = 0
    def failing_insert(self, doc, **kwargs):
        nonlocal calls
        if self.name == 'fact_table':
            calls += 1
        if self.name == 'fact_table' and calls == 2:
            raise RuntimeError('synthetic second insert failure')
        return original(self, doc, **kwargs)
    monkeypatch.setattr(Collection, 'insert_one', failing_insert)
    assert backend.process(raw_id) == 0
    assert backend.db.fact_table.count_documents({'raw_id': raw_id}) == 0
    assert backend.db.pipeline_status.find_one({'raw_id': raw_id})['status'] == 'FAILED'
    assert backend.published_offers() == []

def test_status_commit_failure_rolls_back_facts(backend, monkeypatch):
    raw_id = backend.ingest('@test', '3', 'synthetic')
    original = Collection.update_one
    def failing_update(self, filter, update, **kwargs):
        if self.name == 'pipeline_status' and kwargs.get('session') is not None:
            raise RuntimeError('synthetic status failure')
        return original(self, filter, update, **kwargs)
    monkeypatch.setattr(Collection, 'update_one', failing_update)
    assert backend.process(raw_id) == 0
    assert backend.db.fact_table.count_documents({'raw_id': raw_id}) == 0
    assert backend.db.pipeline_status.find_one({'raw_id': raw_id})['status'] == 'FAILED'

def test_failed_message_cannot_retry(backend, monkeypatch):
    original = Collection.insert_one
    raw_id = backend.ingest('@test', '4', 'synthetic')
    def failing_insert(self, doc, **kwargs):
        if self.name == 'fact_table':
            raise RuntimeError('synthetic write failure')
        return original(self, doc, **kwargs)
    monkeypatch.setattr(Collection, 'insert_one', failing_insert)
    assert backend.process(raw_id) == 0
    with pytest.raises(RuntimeError, match='Only PENDING'):
        backend.process(raw_id)
