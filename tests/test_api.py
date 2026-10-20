import json
import threading
from datetime import datetime, timezone
from http.client import HTTPConnection
from http.server import HTTPServer

import pytest

from superdeal.api import get_deal, list_deals, make_handler, record_click
from superdeal.database import connect, upsert_deal


def seed_db():
    db = connect(":memory:", check_same_thread=False)
    now = datetime.now(timezone.utc).isoformat()
    upsert_deal(
        db, duplicate_hash="a", product_name="OnePlus Pad 2", deal_price=29699,
        merchant="Amazon", source_url="https://amazon.in/pad", affiliate_url="https://earnkaro.example/pad", raw_text="Pad",
        observed_at=now,
    )
    upsert_deal(
        db, duplicate_hash="b", product_name="Wonderchef Cooktop", deal_price=3499,
        merchant="Flipkart", source_url="https://flipkart.com/cook", affiliate_url="https://earnkaro.example/cook", raw_text="Cooktop",
        observed_at=now,
    )
    return db


def test_list_deals_filters_sort_and_limits():
    db = seed_db()
    assert len(list_deals(db, q="pad")) == 1
    assert len(list_deals(db, merchant="amazon")) == 1
    assert len(list_deals(db, min_price=3000, max_price=4000)) == 1
    assert list_deals(db, sort="price_asc")[0]["product_name"] == "Wonderchef Cooktop"
    assert list_deals(db, sort="price_desc")[0]["product_name"] == "OnePlus Pad 2"
    assert len(list_deals(db, limit=1)) == 1
    assert get_deal(db, 999) is None


def test_click_tracking_counts_and_returns_affiliate_url():
    db = seed_db()
    db.execute("UPDATE deals SET affiliate_url = ? WHERE id = 1", ("https://example.com/affiliate",))
    db.commit()
    assert record_click(db, 1) == "https://example.com/affiliate"
    assert list_deals(db, sort="popular")[0]["click_count"] == 1


def test_click_does_not_fall_back_to_raw_source_url():
    db = seed_db()
    db.execute("UPDATE deals SET affiliate_url = NULL WHERE id = 1")
    db.commit()
    assert record_click(db, 1) is None


def test_invalid_filters_raise():
    db = seed_db()
    with pytest.raises(ValueError, match="sort"):
        list_deals(db, sort="random")
    with pytest.raises(ValueError, match="min_price"):
        list_deals(db, min_price=4000, max_price=3000)


def test_http_api_health_list_detail_and_filter_errors():
    db = seed_db()
    server = HTTPServer(("127.0.0.1", 0), make_handler(db))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = HTTPConnection("127.0.0.1", server.server_port)
        client.request("GET", "/health")
        response = client.getresponse()
        assert response.status == 200
        assert json.loads(response.read())["status"] == "ok"

        client.request("GET", "/deals?q=OnePlus&min_price=20000&sort=price_desc")
        response = client.getresponse()
        payload = json.loads(response.read())
        assert response.status == 200
        assert payload["deals"][0]["product_name"] == "OnePlus Pad 2"
        assert "source_url" not in payload["deals"][0]
        assert "description" in payload["deals"][0]
        assert "brand" in payload["deals"][0]
        assert "mrp" in payload["deals"][0]
        assert "enrichment_status" in payload["deals"][0]

        client.request("GET", "/deals/1")
        response = client.getresponse()
        payload = json.loads(response.read())
        assert response.status == 200
        assert payload["merchant"] == "Amazon"
        assert "description" in payload
        assert "brand" in payload
        assert "mrp" in payload
        assert "enrichment_status" in payload
        assert "source_url" not in payload

        client.request("GET", "/deals/1/freshness")
        response = client.getresponse()
        payload = json.loads(response.read())
        assert response.status == 200
        assert payload["deal_id"] == 1
        assert "status" in payload
        assert "age_hours" in payload

        client.request("GET", "/deals?sort=invalid")
        response = client.getresponse()
        assert response.status == 400

        client.request("GET", "/deals?min_price=4000&max_price=3000")
        response = client.getresponse()
        assert response.status == 400

        client.request("GET", "/deals/1/price-history")
        response = client.getresponse()
        payload = json.loads(response.read())
        assert response.status == 200
        assert payload["history"][0]["price"] == 29699

        client.request("GET", "/deals/1/intelligence")
        response = client.getresponse()
        payload = json.loads(response.read())
        assert response.status == 200
        assert payload["is_historical_low"] is True

        client.request("GET", "/deals/999")
        response = client.getresponse()
        assert response.status == 404

        client.request("GET", "/unknown")
        response = client.getresponse()
        assert response.status == 404

        client.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
