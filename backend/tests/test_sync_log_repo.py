"""Integration test: sync_log_repo against the real test schema."""
import pytest

from backend.repositories import sync_log_repo


pytestmark = pytest.mark.usefixtures("clean_test_tables")


def test_get_last_synced_returns_none_when_empty():
    assert sync_log_repo.get_last_synced_trade_id(schema="test") is None


def test_insert_success_then_get_returns_trade_id():
    sync_log_repo.insert(last_trade_id="T1", status="success", schema="test")
    assert sync_log_repo.get_last_synced_trade_id(schema="test") == "T1"


def test_get_last_synced_skips_error_rows():
    sync_log_repo.insert(last_trade_id="T1", status="success", schema="test")
    sync_log_repo.insert(last_trade_id=None, status="error", error_message="boom", schema="test")
    assert sync_log_repo.get_last_synced_trade_id(schema="test") == "T1"


def test_get_last_synced_returns_most_recent_success():
    sync_log_repo.insert(last_trade_id="T1", status="success", schema="test")
    sync_log_repo.insert(last_trade_id="T2", status="success", schema="test")
    assert sync_log_repo.get_last_synced_trade_id(schema="test") == "T2"
