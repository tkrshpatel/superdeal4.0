"""Synthetic Phase 6 integration checks; requires local MongoDB rs0."""
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pymongo import MongoClient
from bson import ObjectId
from backend import Backend
from api import _legacy_deal


def test_public_metadata_clicks_and_freshness():
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/?replicaSet=rs0'), serverSelectionTimeoutMS=5000)
    db = client['superdeal_phase6_test_' + uuid4().hex]
    try:
        backend = Backend(db)
        backend.setup()
        raw_id, oid, pub_id = ObjectId(), ObjectId(), uuid4().hex
        db.fact_table.insert_one({'_id': oid, 'raw_id': raw_id, 'publication_id': pub_id, 'offer_index': 0,
                                  'product': {'product_name': 'Synthetic', 'affiliate_urls': ['https://example.com/x']}})
        db.pipeline_status.insert_one({'raw_id': raw_id, 'publication_id': pub_id, 'status': 'PUBLISHED',
                                       'published_at': datetime.now(timezone.utc)})
        metadata = backend.public_metadata(str(oid))
        assert metadata['click_count'] == 0 and metadata['hot'] is False and metadata['fresh'] is True
        for _ in range(5):
            backend.record_affiliate_click(str(oid))
        metadata = backend.public_metadata(str(oid))
        assert metadata['click_count'] == 5 and metadata['hot'] is False  # Clicks alone do not establish a discount.
        legacy = _legacy_deal({'id': str(oid), 'product_name': 'Synthetic', 'affiliate_urls': ['https://example.com/x']}, metadata)
        assert legacy['last_seen_at'] is not None and legacy['click_count'] == 5
        assert legacy['affiliate_url'] == 'https://example.com/x'
    finally:
        client.drop_database(db.name)
        client.close()


def test_unpublished_fact_has_no_metadata():
    client = MongoClient(os.getenv('MONGODB_URI', 'mongodb://127.0.0.1:27017/?replicaSet=rs0'), serverSelectionTimeoutMS=5000)
    db = client['superdeal_phase6_test_' + uuid4().hex]
    try:
        backend = Backend(db)
        oid = ObjectId()
        db.fact_table.insert_one({'_id': oid, 'raw_id': ObjectId(), 'publication_id': 'test'})
        assert backend.public_metadata(str(oid)) is None
        assert backend.public_metadata('not-an-id') is None
    finally:
        client.drop_database(db.name)
        client.close()
