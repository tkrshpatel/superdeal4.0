"""Feed eligibility must be filtered in MongoDB before sorting/limiting."""
from datetime import datetime, timedelta, timezone
import pytest
import backend as module
from backend import Backend

AT = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)

class Facts:
    def aggregate(self, pipeline):
        self.pipeline = pipeline
        return []

@pytest.mark.parametrize('sort', ['newest', 'price_asc', 'price_desc', 'popular'])
def test_feed_window_precedes_sort_and_limit(monkeypatch, sort):
    facts = Facts()
    db = type('DB', (), {'fact_table': facts})()
    monkeypatch.setattr(module, 'now', lambda: AT)
    Backend(db).legacy_search(limit=100, sort=sort, q='iPhone')
    pipeline = facts.pipeline
    window = next((i, stage['$match']['$and']) for i, stage in enumerate(pipeline)
                  if '$match' in stage and '$and' in stage['$match'])
    assert {'_publication.published_at': {'$gte': AT-timedelta(hours=24), '$lte': AT}} in window[1]
    assert window[0] < next(i for i,s in enumerate(pipeline) if '$sort' in s)
    assert window[0] < next(i for i,s in enumerate(pipeline) if '$limit' in s)
    assert any(s.get('$match',{}).get('_publication.status') == 'PUBLISHED' for s in pipeline)
