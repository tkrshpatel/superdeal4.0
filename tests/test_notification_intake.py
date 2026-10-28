"""Get Notified stores private preferences without SMTP or delivery queues."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import mongomock
import pytest
from notifications import NotificationRequests

REQUEST = {'product': 'Headphones', 'email': 'Buyer@example.com',
           'daily_limit': 2, 'days': 7, 'consent': True}


def test_request_stores_timestamp_preferences_and_never_invokes_mailer(monkeypatch):
    monkeypatch.setenv('SUPERDEAL_EMAIL_MODE', 'smtp')
    monkeypatch.delenv('SUPERDEAL_SMTP_PASSWORD', raising=False)
    db = mongomock.MongoClient(tz_aware=True).db
    service = NotificationRequests(db)
    at = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
    with patch('notifications.Mailer', side_effect=AssertionError('No email for intake')):
        service.setup()
        service.save(REQUEST, at=at)
    saved = db.notification_table.find_one({})
    assert saved['ds'] == saved['created_at'] == at
    assert saved['product'] == 'Headphones' and saved['email'] == 'buyer@example.com'
    assert saved['daily_limit'] == 2 and saved['days'] == 7
    assert saved['consent'] is True and saved['consent_at'] == at
    assert saved['status'] == 'saved' and saved['delivery_enabled'] is False
    assert saved['email_verified'] is False
    assert db.alert_confirmations.count_documents({}) == 0
    assert db.deal_alerts.count_documents({}) == 0


def test_repeat_request_updates_preferences_and_preserves_first_submission():
    db = mongomock.MongoClient(tz_aware=True).db
    service = NotificationRequests(db)
    at = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
    service.save(REQUEST, at=at)
    service.save({**REQUEST, 'email':'buyer@example.com', 'days':14, 'daily_limit':3},
                 at=at+timedelta(minutes=5))
    assert db.notification_table.count_documents({}) == 1
    saved = db.notification_table.find_one({})
    assert saved['created_at'] == at and saved['ds'] == at+timedelta(minutes=5)
    assert saved['days'] == 14 and saved['daily_limit'] == 3
    assert saved['submission_count'] == 2
    service.save({**REQUEST, 'product':'Shoes'}, at=at)
    assert db.notification_table.count_documents({}) == 2


def test_invalid_request_cannot_create_a_record():
    db = mongomock.MongoClient().db
    with pytest.raises(ValueError):
        NotificationRequests(db).save({**REQUEST, 'consent':False})
    assert db.notification_table.count_documents({}) == 0
