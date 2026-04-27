"""Integration test: ohlc_cache_repo against the real test schema."""
import pytest

from backend.repositories import ohlc_cache_repo


pytestmark = pytest.mark.usefixtures("clean_test_tables")


def test_get_by_pair_returns_empty_dict_when_empty():
    assert ohlc_cache_repo.get_by_pair("ETHAUD", schema="test") == {}


def test_upsert_then_read_round_trip():
    rows = [
        {"pair": "ETHAUD", "date": "2026-04-01", "close_price": 4000.0},
        {"pair": "ETHAUD", "date": "2026-04-02", "close_price": 4100.0},
    ]
    ohlc_cache_repo.upsert(rows, schema="test")
    result = ohlc_cache_repo.get_by_pair("ETHAUD", schema="test")
    assert result == {"2026-04-01": 4000.0, "2026-04-02": 4100.0}


def test_get_by_pair_filters_by_pair():
    ohlc_cache_repo.upsert(
        [
            {"pair": "ETHAUD", "date": "2026-04-01", "close_price": 4000.0},
            {"pair": "SOLAUD", "date": "2026-04-01", "close_price": 200.0},
        ],
        schema="test",
    )
    assert ohlc_cache_repo.get_by_pair("ETHAUD", schema="test") == {"2026-04-01": 4000.0}
    assert ohlc_cache_repo.get_by_pair("SOLAUD", schema="test") == {"2026-04-01": 200.0}
