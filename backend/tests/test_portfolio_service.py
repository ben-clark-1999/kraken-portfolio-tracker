from decimal import Decimal
from unittest.mock import patch

from backend.services.portfolio_service import (
    calculate_summary,
    get_dca_history,
    calculate_next_dca_date,
    get_balance_change,
)
from backend.models.portfolio import PortfolioSummary
from backend.models.snapshot import PortfolioSnapshot, SnapshotAsset
from backend.models.trade import Lot, DCAEntry
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

AEST = ZoneInfo("Australia/Sydney")


def _lot(asset: str, qty: float, cost_per_unit: float, acquired_days_ago: int, trade_id: str) -> Lot:
    acquired_at = (datetime.now(tz=AEST) - timedelta(days=acquired_days_ago)).isoformat()
    return Lot(
        id="test-id",
        asset=asset,
        acquired_at=acquired_at,
        quantity=qty,
        cost_aud=qty * cost_per_unit,
        cost_per_unit_aud=cost_per_unit,
        kraken_trade_id=trade_id,
        remaining_quantity=qty,
    )


def test_calculate_summary_single_asset():
    balances = {"ETH": Decimal("1.0")}
    prices = {"ETH": Decimal("4000.00")}
    lots = [_lot("ETH", 1.0, 3000.00, 30, "t1")]

    summary = calculate_summary(balances, prices, lots)

    assert summary.total_value_aud == 4000.00
    assert len(summary.positions) == 1
    eth = summary.positions[0]
    assert eth.asset == "ETH"
    assert eth.value_aud == 4000.00
    assert eth.cost_basis_aud == 3000.00
    assert abs(eth.unrealised_pnl_aud - 1000.00) < 0.01
    assert eth.allocation_pct == 100.0


def test_calculate_summary_allocation_pct():
    balances = {"ETH": Decimal("1.0"), "SOL": Decimal("10.0")}
    prices = {"ETH": Decimal("2000.00"), "SOL": Decimal("200.00")}
    lots = [
        _lot("ETH", 1.0, 1800.00, 30, "t1"),
        _lot("SOL", 10.0, 150.00, 20, "t2"),
    ]

    summary = calculate_summary(balances, prices, lots)

    assert summary.total_value_aud == 4000.00  # 2000 ETH + 2000 SOL
    eth = next(p for p in summary.positions if p.asset == "ETH")
    sol = next(p for p in summary.positions if p.asset == "SOL")
    assert eth.allocation_pct == 50.0
    assert sol.allocation_pct == 50.0


def test_calculate_summary_negative_pnl():
    balances = {"ETH": Decimal("1.0")}
    prices = {"ETH": Decimal("2000.00")}
    lots = [_lot("ETH", 1.0, 3000.00, 30, "t1")]

    summary = calculate_summary(balances, prices, lots)

    eth = summary.positions[0]
    assert eth.unrealised_pnl_aud < 0
    assert abs(eth.unrealised_pnl_aud - (-1000.00)) < 0.01


def test_get_dca_history():
    prices = {"ETH": Decimal("4000.00")}
    lots = [
        _lot("ETH", 0.5, 2000.00, 60, "t1"),
        _lot("ETH", 0.5, 3000.00, 30, "t2"),
    ]

    entries = get_dca_history(lots, prices)

    assert len(entries) == 2
    assert all(e.asset == "ETH" for e in entries)
    first = entries[0]  # oldest first
    assert first.current_value_aud == 0.5 * 4000.00
    assert abs(first.unrealised_pnl_aud - (2000.00 - 1000.00)) < 0.01


def test_calculate_next_dca_date():
    lots = [
        _lot("ETH", 1.0, 3000.00, 14, "t1"),
        _lot("SOL", 10.0, 200.00, 7, "t2"),   # most recent: 7 days ago
    ]
    next_date = calculate_next_dca_date(lots)
    expected = (datetime.now(tz=AEST) - timedelta(days=7) + timedelta(days=7)).date()
    assert next_date == expected  # most recent lot + 7 days = today


def test_calculate_next_dca_date_empty():
    assert calculate_next_dca_date([]) is None


# --- get_balance_change tests ---


def _mock_summary(total: float, captured_at: str = "2026-04-20T10:00:00+10:00"):
    return PortfolioSummary(
        total_value_aud=total,
        positions=[],
        captured_at=captured_at,
        next_dca_date=None,
    )


def _mock_snapshot(total: float, captured_at: str):
    return PortfolioSnapshot(
        id="snap-1",
        captured_at=captured_at,
        total_value_aud=total,
        assets={},
    )


@patch("backend.services.portfolio_service.snapshot_service")
@patch("backend.services.portfolio_service.build_summary")
def test_get_balance_change_1w(mock_build, mock_snap):
    mock_build.return_value = _mock_summary(5000.00)
    mock_snap.get_nearest_snapshot.return_value = _mock_snapshot(
        4500.00, "2026-04-13T10:00:00+10:00"
    )

    result = get_balance_change("1W")

    assert result.timeframe == "1W"
    assert result.start_value_aud == 4500.00
    assert result.end_value_aud == 5000.00
    assert result.change_aud == 500.00
    assert abs(result.change_pct - 11.11) < 0.1
    assert result.note is None


@patch("backend.services.portfolio_service.snapshot_service")
@patch("backend.services.portfolio_service.build_summary")
def test_get_balance_change_all(mock_build, mock_snap):
    mock_build.return_value = _mock_summary(5000.00)
    mock_snap.get_oldest_snapshot.return_value = _mock_snapshot(
        2000.00, "2025-12-01T10:00:00+11:00"
    )

    result = get_balance_change("ALL")

    assert result.timeframe == "ALL"
    assert result.start_value_aud == 2000.00
    assert result.change_aud == 3000.00
    assert result.change_pct == 150.00
    assert result.note is None


@patch("backend.services.portfolio_service.snapshot_service")
@patch("backend.services.portfolio_service.build_summary")
def test_get_balance_change_fallback_to_oldest(mock_build, mock_snap):
    mock_build.return_value = _mock_summary(5000.00)
    mock_snap.get_nearest_snapshot.return_value = None
    mock_snap.get_oldest_snapshot.return_value = _mock_snapshot(
        3000.00, "2026-03-01T10:00:00+11:00"
    )

    result = get_balance_change("3M")

    assert result.note is not None
    assert "oldest available" in result.note
    assert result.start_value_aud == 3000.00


@patch("backend.services.portfolio_service.snapshot_service")
@patch("backend.services.portfolio_service.build_summary")
def test_get_balance_change_no_snapshots(mock_build, mock_snap):
    mock_build.return_value = _mock_summary(5000.00)
    mock_snap.get_nearest_snapshot.return_value = None
    mock_snap.get_oldest_snapshot.return_value = None

    result = get_balance_change("1M")

    assert result.start_value_aud == 0
    assert result.end_value_aud == 5000.00
    assert result.note == "No historical snapshots available."


@patch("backend.services.portfolio_service.snapshot_service")
@patch("backend.services.portfolio_service.build_summary")
def test_get_balance_change_negative(mock_build, mock_snap):
    mock_build.return_value = _mock_summary(3000.00)
    mock_snap.get_nearest_snapshot.return_value = _mock_snapshot(
        5000.00, "2026-04-13T10:00:00+10:00"
    )

    result = get_balance_change("1W")

    assert result.change_aud == -2000.00
    assert result.change_pct == -40.00
