"""Real MongoDB integration tests. Never touches the production database."""
import os
from uuid import uuid4

import pytest
from pymongo import MongoClient
from backend import Backend


@pytest.fixture
def backend():
    uri = os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017')
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    # Unique temporary DB per test. Never use superdeal or a shared database.
    name = 'superdeal_test_' + uuid4().hex
    db = client[name]
    instance = Backend(db)
    instance.setup()
    try:
        yield instance
    finally:
        client.drop_database(name)
        client.close()


def product(url, name='Example headphones'):
    return dict(product_name=name, brand='Example', ecommerce_platform='Amazon',
                deal_price=999, original_price=1999, discount_percentage=50,
                affiliate_urls=[url], confidence=95, issues=[])


def result(*products, unassigned=None):
    return dict(products=list(products), unassigned_urls=unassigned or [],
                message_issues=[], analysis_summary='Test')


def test_setup_creates_five_collections(backend):
    assert {'raw', 'ek_raw', 'fact_table', 'pipeline_status', 'pipeline_logs'} <= set(backend.db.list_collection_names())


def test_ingestion_idempotent(backend):
    first = backend.ingest('@sample', '123', 'A sample deal')
    second = backend.ingest('@sample', '123', 'A different message')
    assert first == second
    assert backend.db.raw.count_documents({}) == 1
    assert backend.db.pipeline_status.count_documents({}) == 1
    assert backend.db.raw.find_one({'_id': first})['text'] == 'A sample deal'


def test_two_products_publish_together(backend):
    a, b = 'https://example.com/a', 'https://example.com/b'
    text = f'A {a} B {b}'
    backend.converter = lambda _: {'response_text': text, 'response_payload': {'data': text}}
    backend.llm = lambda _: result(product(a, 'Product A'), product(b, 'Product B'))
    raw_id = backend.ingest('@sample', '124', 'Original Telegram message')
    assert backend.process(raw_id) == 2
    assert len(backend.published_offers()) == 2
    assert backend.db.pipeline_status.find_one({'raw_id': raw_id})['status'] == 'PUBLISHED'
    assert backend.db.ek_raw.find_one({'raw_id': raw_id})['response_payload'] == {'data': text}
    assert backend.db.pipeline_logs.count_documents({'raw_id': raw_id}) >= 4


def test_invalid_second_product_blocks_everything(backend):
    a, b = 'https://example.com/a', 'https://example.com/b'
    text = f'A {a} B {b}'
    backend.converter = lambda _: {'response_text': text, 'response_payload': {'data': text}}
    backend.llm = lambda _: result(product(a), product('https://invented.example/other'))
    raw_id = backend.ingest('@sample', '125', 'Original Telegram message')
    assert backend.process(raw_id) == 0
    assert backend.db.pipeline_status.find_one({'raw_id': raw_id})['status'] == 'FAILED'
    assert backend.db.fact_table.count_documents({'raw_id': raw_id}) == 0
    assert backend.published_offers() == []
    assert backend.db.pipeline_logs.count_documents({'raw_id': raw_id, 'severity': 'ERROR'}) >= 1


def test_failed_conversion_not_retried(backend):
    calls = []
    def fail(_):
        calls.append(True)
        raise RuntimeError('Simulated EarnKaro outage')
    backend.converter = fail
    raw_id = backend.ingest('@sample', '126', 'Original Telegram message')
    assert backend.process(raw_id) == 0
    assert backend.db.pipeline_status.find_one({'raw_id': raw_id})['status'] == 'FAILED'
    with pytest.raises(RuntimeError, match='Only PENDING'):
        backend.process(raw_id)
    assert len(calls) == 1
    assert backend.published_offers() == []


def test_unpublished_staged_facts_are_invisible(backend):
    raw_id = backend.ingest('@sample', '127', 'Original Telegram message')
    backend.db.fact_table.insert_one({'raw_id': raw_id, 'offer_index': 0,
                                      'publication_id': 'staged', 'product': product('https://example.com/a')})
    assert backend.published_offers() == []
