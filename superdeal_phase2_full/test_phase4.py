"""Phase 4: real MongoDB publication-gated pagination/detail; no external services."""
import os
from uuid import uuid4
from pymongo import MongoClient
from backend import Backend


def test_database_pagination_and_visibility():
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/?replicaSet=rs0'), serverSelectionTimeoutMS=5000)
    name = 'superdeal_test_phase4_' + uuid4().hex
    backend = Backend(client[name])
    try:
        backend.setup()
        for i in range(4):
            url = 'https://example.com/affiliate-' + str(i)
            backend.converter = lambda _, u=url: {'response_text': u, 'response_payload': {'data': u}}
            backend.llm = lambda _, u=url, n=i: {'products': [{'product_name': 'Test ' + str(n), 'brand': None, 'ecommerce_platform': None, 'deal_price': 100, 'original_price': None, 'discount_percentage': None, 'affiliate_urls': [u], 'confidence': 90, 'issues': []}], 'unassigned_urls': [], 'message_issues': [], 'analysis_summary': ''}
            rid = backend.ingest('@phase4', str(i), 'synthetic')
            assert backend.process(rid) == 1
        first = backend.published_page(limit=2, offset=0)
        second = backend.published_page(limit=2, offset=2)
        assert first['has_more'] and not second['has_more']
        assert len(first['items']) == len(second['items']) == 2
        assert len({x['id'] for x in first['items'] + second['items']}) == 4
        for item in first['items'] + second['items']:
            assert backend.published_offer_by_id(item['id']) == item
        assert backend.published_offer_by_id('bad-id') is None
        assert backend.published_page(limit=2, offset=100)['items'] == []
        # A raw fact with no PUBLISHED status must not leak.
        from bson import ObjectId
        fake = backend.db.fact_table.insert_one({'raw_id': ObjectId(), 'offer_index': 0, 'publication_id': 'fake', 'product': {'product_name': 'hidden'}}).inserted_id
        assert backend.published_offer_by_id(str(fake)) is None
        assert len(backend.published_page(limit=100)['items']) == 4
    finally:
        client.drop_database(name)
        client.close()
