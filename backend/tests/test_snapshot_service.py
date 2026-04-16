from decimal import Decimal
from backend.services.snapshot_service import save_snapshot, get_snapshots, should_snapshot
from backend.models.portfolio import PortfolioSummary, AssetPosition
from backend.utils.timezone import now_aest, to_iso
from datetime import timedelta


def _make_summary() -> PortfolioSummary:
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
        captured_at=to_iso(now_aest()),
        next_dca_date=None,
    )


def test_save_and_retrieve_snapshot(test_db):
    save_snapshot(_make_summary(), schema="test")
    snapshots = get_snapshots(schema="test")
    assert len(snapshots) == 1
    assert snapshots[0].total_value_aud == 5000.00
    assert "ETH" in snapshots[0].assets


def test_should_snapshot_true_when_no_recent_snapshot(test_db):
    assert should_snapshot(schema="test") is True


def test_should_snapshot_false_when_recent_snapshot_exists(test_db):
    save_snapshot(_make_summary(), schema="test")
    assert should_snapshot(schema="test") is False


def test_get_snapshots_returns_time_range(test_db):
    save_snapshot(_make_summary(), schema="test")
    from_dt = to_iso(now_aest() - timedelta(hours=1))
    to_dt = to_iso(now_aest() + timedelta(hours=1))
    snapshots = get_snapshots(from_dt=from_dt, to_dt=to_dt, schema="test")
    assert len(snapshots) == 1
