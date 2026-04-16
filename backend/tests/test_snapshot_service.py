from datetime import timedelta
from backend.services.snapshot_service import save_snapshot, get_snapshots, should_snapshot
from backend.models.portfolio import PortfolioSummary, AssetPosition
from backend.utils.timezone import now_aest, to_iso


def _make_summary(captured_at: str | None = None) -> PortfolioSummary:
    return PortfolioSummary(
        total_value_aud=5000.00,
        positions=[
            AssetPosition(
                asset="ETH",
                quantity=1.0,
                price_aud=5000.00,
                value_aud=5000.00,
                cost_basis_aud=3000.00,
                unrealised_pnl_aud=2000.00,
                allocation_pct=100.0,
            )
        ],
        captured_at=captured_at or to_iso(now_aest()),
        next_dca_date=None,
    )


def test_save_and_retrieve_snapshot(clean_test_tables):
    save_snapshot(_make_summary(), schema="test")
    snapshots = get_snapshots(schema="test")
    assert len(snapshots) == 1
    assert snapshots[0].total_value_aud == 5000.00
    assert "ETH" in snapshots[0].assets


def test_should_snapshot_true_when_no_recent_snapshot(clean_test_tables):
    assert should_snapshot(schema="test") is True


def test_should_snapshot_false_when_recent_snapshot_exists(clean_test_tables):
    save_snapshot(_make_summary(), schema="test")
    assert should_snapshot(schema="test") is False


def test_get_snapshots_filters_by_time_range(clean_test_tables):
    captured = now_aest()
    save_snapshot(_make_summary(captured_at=to_iso(captured)), schema="test")

    # Window that excludes the snapshot (entirely before it)
    before_from = to_iso(captured - timedelta(hours=2))
    before_to = to_iso(captured - timedelta(hours=1))
    excluded = get_snapshots(from_dt=before_from, to_dt=before_to, schema="test")
    assert len(excluded) == 0

    # Window that includes the snapshot
    inclusive_from = to_iso(captured - timedelta(minutes=5))
    inclusive_to = to_iso(captured + timedelta(minutes=5))
    included = get_snapshots(from_dt=inclusive_from, to_dt=inclusive_to, schema="test")
    assert len(included) == 1
