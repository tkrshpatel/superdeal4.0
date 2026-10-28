"""Publication/freshness parity and bounded metadata queries for a whole page."""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import mongomock
from bson import ObjectId
from backend import Backend


def test_batch_metadata_matches_individual_cards_and_keeps_publication_gate():
    db = mongomock.MongoClient().feed
    backend = Backend(db)
    current = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
    ids = []
    for i in range(48):
        raw, oid = ObjectId(), ObjectId()
        ids.append(str(oid))
        db.fact_table.insert_one({
            '_id': oid, 'raw_id': raw, 'publication_id': 'active',
            'product': {'deal_price': 20, 'original_price': 100},
            'offer_facts': {'version': 11, 'current_price': 20, 'mrp': 100,
                            'discount_pct': 80, 'discount_kind': 'exact'},
        })
        db.pipeline_status.insert_one({
            'raw_id': raw, 'publication_id': 'active' if i != 46 else 'replaced',
            'status': 'PUBLISHED' if i != 47 else 'PENDING',
            'published_at': current-timedelta(minutes=i*10),
        })
        db.deal_clicks.insert_many([
            {'deal_id': str(oid), 'clicked_at': current-timedelta(minutes=5)},
            {'deal_id': str(oid), 'clicked_at': current-timedelta(days=2)},
        ])
    with patch('backend.now', return_value=current):
        expected = {key: backend.public_metadata(key) for key in ids}
        with patch.object(db.fact_table, 'find', wraps=db.fact_table.find) as facts, \
             patch.object(db.pipeline_status, 'find', wraps=db.pipeline_status.find) as statuses, \
             patch.object(db.deal_clicks, 'aggregate', wraps=db.deal_clicks.aggregate) as clicks:
            result = backend.public_metadata_many(ids + ['bad-id'])
            assert facts.call_count == statuses.call_count == clicks.call_count == 1
        assert result == {key: value for key, value in expected.items() if value is not None}
        assert result[ids[0]]['hot'] is True
        assert result[ids[24]]['hot'] is True  # Exactly four hours.
        assert result[ids[25]]['hot'] is False
        assert result[ids[31]]['hot'] is False
        assert all(value['click_count'] == 1 for value in result.values())
        assert ids[46] not in result and ids[47] not in result


def test_empty_metadata_page_does_not_query_database():
    backend = Backend(mongomock.MongoClient().feed)
    with patch.object(backend.db.fact_table, 'find') as query:
        assert backend.public_metadata_many(['bad-id']) == {}
        query.assert_not_called()
