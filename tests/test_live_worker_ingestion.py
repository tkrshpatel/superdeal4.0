"""Ensure Telegram ingestion does not wait for slow deal processing."""
from unittest.mock import MagicMock
from superdeal_local_live_worker import ingest_message, handle_message


def test_ingest_message_saves_raw_without_running_pipeline():
    backend = MagicMock()
    backend.ingest.return_value = "raw-123"
    backend.db.pipeline_status.find_one.return_value = {"status": "PENDING"}
    state, raw_id = ingest_message(
        backend, "telegram:123", "99", "sample deal", None
    )
    assert (state, raw_id) == ("PENDING", "raw-123")
    backend.ingest.assert_called_once_with(
        "telegram:123", "99", "sample deal", observed_at=None
    )
    backend.process.assert_not_called()


def test_synchronous_compatibility_handler_still_processes_once():
    backend = MagicMock()
    backend.ingest.return_value = "raw-123"
    backend.db.pipeline_status.find_one.side_effect = [
        {"status": "PENDING"}, {"status": "PUBLISHED"}, {"status": "PUBLISHED"}
    ]
    backend.process.return_value = 1
    state, raw_id = handle_message(
        backend, "telegram:123", "99", "sample deal", None
    )
    assert (state, raw_id) == ("PUBLISHED", "raw-123")
    backend.process.assert_called_once_with("raw-123")
