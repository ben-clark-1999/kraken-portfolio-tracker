"""Integration test: lots_repo against the real test schema."""
import pytest

from backend.repositories import lots_repo


# These tests use the test schema — see conftest.py:clean_test_tables.
pytestmark = pytest.mark.usefixtures("clean_test_tables")


def _row(trade_id: str, asset: str = "ETH", qty: str = "0.1") -> dict:
    return {
        "asset": asset,
        "acquired_at": "2026-04-01T10:00:00+10:00",
        "quantity": qty,
        "cost_aud": "100.00",
        "cost_per_unit_aud": "1000.00",
        "kraken_trade_id": trade_id,
        "remaining_quantity": qty,
    }


def test_get_all_returns_empty_when_no_lots():
    result = lots_repo.get_all(schema="test")
    assert result == []


def test_insert_then_get_all_round_trip():
    lots_repo.insert([_row("T1"), _row("T2")], schema="test")
    result = lots_repo.get_all(schema="test")
    assert len(result) == 2
    trade_ids = {l.kraken_trade_id for l in result}
    assert trade_ids == {"T1", "T2"}


def test_get_existing_trade_ids_filters_correctly():
    lots_repo.insert([_row("T1"), _row("T2")], schema="test")
    existing = lots_repo.get_existing_trade_ids(["T1", "T3", "T4"], schema="test")
    assert existing == {"T1"}


def test_get_existing_trade_ids_empty_input_returns_empty_set():
    """Don't query the DB when there's nothing to check."""
    result = lots_repo.get_existing_trade_ids([], schema="test")
    assert result == set()
