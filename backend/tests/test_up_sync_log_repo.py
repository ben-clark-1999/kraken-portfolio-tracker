from datetime import datetime, timezone

import pytest
from backend.db.supabase_client import get_supabase
from backend.repositories import up_sync_log_repo

SCHEMA = "test"


@pytest.fixture(autouse=True)
def _truncate():
    get_supabase().schema(SCHEMA).table("up_sync_log").delete().neq(
        "id", "00000000-0000-0000-0000-000000000001"
    ).execute()
    yield


def test_record_start_then_finalize_success():
    sync_id = up_sync_log_repo.record_start(schema=SCHEMA)
    latest = up_sync_log_repo.latest(schema=SCHEMA)
    assert latest["status"] == "in_progress"
    up_sync_log_repo.finalize_success(
        sync_id, last_seen_tx_at=datetime(2026, 4, 1, tzinfo=timezone.utc), schema=SCHEMA,
    )
    latest = up_sync_log_repo.latest(schema=SCHEMA)
    assert latest["status"] == "success"
    assert latest["last_seen_tx_at"] is not None


def test_record_start_then_finalize_error():
    sync_id = up_sync_log_repo.record_start(schema=SCHEMA)
    up_sync_log_repo.finalize_error(sync_id, error_message="boom", schema=SCHEMA)
    latest = up_sync_log_repo.latest(schema=SCHEMA)
    assert latest["status"] == "error"
    assert latest["error_message"] == "boom"


def test_last_successful_returns_none_when_empty():
    assert up_sync_log_repo.last_successful_seen_tx_at(schema=SCHEMA) is None


def test_last_successful_returns_latest_seen_tx_at():
    sid = up_sync_log_repo.record_start(schema=SCHEMA)
    up_sync_log_repo.finalize_success(
        sid, last_seen_tx_at=datetime(2026, 4, 1, tzinfo=timezone.utc), schema=SCHEMA,
    )
    sid2 = up_sync_log_repo.record_start(schema=SCHEMA)
    up_sync_log_repo.finalize_success(
        sid2, last_seen_tx_at=datetime(2026, 5, 1, tzinfo=timezone.utc), schema=SCHEMA,
    )
    last = up_sync_log_repo.last_successful_seen_tx_at(schema=SCHEMA)
    assert last is not None and last.month == 5
