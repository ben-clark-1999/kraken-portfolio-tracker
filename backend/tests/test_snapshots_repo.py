"""Integration test: snapshots_repo against the real test schema."""
import pytest

from backend.repositories import snapshots_repo


pytestmark = pytest.mark.usefixtures("clean_test_tables")


def _insert_snapshot(captured_at: str, total: float) -> None:
    snapshots_repo.insert(
        captured_at=captured_at,
        total_value_aud=total,
        assets_json={"ETH": {"quantity": 1.0, "value_aud": total, "price_aud": total}},
        schema="test",
    )


def test_get_all_returns_empty_initially():
    assert snapshots_repo.get_all(from_dt=None, to_dt=None, schema="test") == []


def test_insert_then_get_all_round_trip():
    _insert_snapshot("2026-04-01T10:00:00+10:00", 1000.0)
    _insert_snapshot("2026-04-02T10:00:00+10:00", 1100.0)
    result = snapshots_repo.get_all(from_dt=None, to_dt=None, schema="test")
    assert len(result) == 2
    assert result[0].total_value_aud == 1000.0
    assert result[1].total_value_aud == 1100.0


def test_get_oldest_returns_earliest():
    _insert_snapshot("2026-04-02T10:00:00+10:00", 1100.0)
    _insert_snapshot("2026-04-01T10:00:00+10:00", 1000.0)
    oldest = snapshots_repo.get_oldest(schema="test")
    assert oldest is not None
    assert oldest.total_value_aud == 1000.0


def test_get_oldest_returns_none_when_empty():
    assert snapshots_repo.get_oldest(schema="test") is None


def test_get_existing_dates_returns_yyyy_mm_dd_set():
    _insert_snapshot("2026-04-01T10:00:00+10:00", 1000.0)
    _insert_snapshot("2026-04-02T10:00:00+10:00", 1100.0)
    dates = snapshots_repo.get_existing_dates(schema="test")
    assert dates == {"2026-04-01", "2026-04-02"}


def test_clear_deletes_all_returns_count():
    _insert_snapshot("2026-04-01T10:00:00+10:00", 1000.0)
    _insert_snapshot("2026-04-02T10:00:00+10:00", 1100.0)
    n = snapshots_repo.clear(schema="test")
    assert n == 2
    assert snapshots_repo.get_all(from_dt=None, to_dt=None, schema="test") == []


def test_get_nearest_picks_closest_neighbor():
    _insert_snapshot("2026-04-01T10:00:00+10:00", 1000.0)
    _insert_snapshot("2026-04-10T10:00:00+10:00", 1500.0)
    nearest = snapshots_repo.get_nearest("2026-04-04T10:00:00+10:00", schema="test")
    assert nearest is not None
    assert nearest.total_value_aud == 1000.0  # 3 days vs 6 days → April 1 wins
