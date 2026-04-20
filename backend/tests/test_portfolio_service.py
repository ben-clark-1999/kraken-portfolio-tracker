from decimal import Decimal
from unittest.mock import patch

from backend.services.portfolio_service import (
    calculate_summary,
    get_dca_history,
    calculate_next_dca_date,
    get_balance_change,
    get_dca_analysis,
    get_unrealised_cgt,
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


# --- get_dca_analysis tests ---


@patch("backend.services.portfolio_service.sync_service")
def test_get_dca_analysis_multi_asset(mock_sync):
    mock_sync.get_all_lots.return_value = [
        _lot("ETH", 0.5, 3000.00, 28, "t1"),
        _lot("ETH", 0.5, 3200.00, 21, "t2"),
        _lot("ETH", 0.5, 2800.00, 14, "t3"),
        _lot("SOL", 10.0, 200.00, 14, "t4"),
    ]

    result = get_dca_analysis()

    assert len(result.assets) == 2
    eth = next(a for a in result.assets if a.asset == "ETH")
    sol = next(a for a in result.assets if a.asset == "SOL")

    assert eth.lot_count == 3
    assert eth.total_invested_aud == 0.5 * 3000 + 0.5 * 3200 + 0.5 * 2800
    assert eth.average_cost_basis_aud == eth.total_invested_aud / 1.5
    assert eth.average_days_between_buys == 7.0  # 28→21→14 = gaps of 7 each
    assert eth.cadence_deviation_days == 0.0  # exactly on weekly target

    assert sol.lot_count == 1
    assert sol.average_days_between_buys is None
    assert sol.cadence_deviation_days is None

    assert result.overall["total_invested_aud"] == eth.total_invested_aud + sol.total_invested_aud


@patch("backend.services.portfolio_service.sync_service")
def test_get_dca_analysis_slow_cadence(mock_sync):
    mock_sync.get_all_lots.return_value = [
        _lot("ETH", 0.5, 3000.00, 30, "t1"),
        _lot("ETH", 0.5, 3200.00, 20, "t2"),  # 10-day gap
    ]

    result = get_dca_analysis()
    eth = result.assets[0]

    assert eth.average_days_between_buys == 10.0
    assert eth.cadence_deviation_days == 3.0  # 10 - 7 = 3 days slower


@patch("backend.services.portfolio_service.sync_service")
def test_get_dca_analysis_empty_lots(mock_sync):
    mock_sync.get_all_lots.return_value = []

    result = get_dca_analysis()

    assert result.assets == []
    assert result.overall["total_invested_aud"] == 0
    assert result.overall["average_cadence_days"] is None


# --- get_unrealised_cgt tests ---


def _lot_on_date(asset: str, qty: float, cost: float, acquired_at: str, trade_id: str) -> Lot:
    """Create a lot with a specific acquisition date string."""
    return Lot(
        id=f"lot-{trade_id}",
        asset=asset,
        acquired_at=acquired_at,
        quantity=qty,
        cost_aud=qty * cost,
        cost_per_unit_aud=cost,
        kraken_trade_id=trade_id,
        remaining_quantity=qty,
    )


@patch("backend.services.portfolio_service.now_aest")
@patch("backend.services.portfolio_service.kraken_service")
@patch("backend.services.portfolio_service.sync_service")
def test_cgt_15apr2025_checked_15apr2026_ineligible(mock_sync, mock_kraken, mock_now):
    """Buy 15/04/2025, check 15/04/2026 → exactly 12 months, NOT eligible."""
    mock_now.return_value = datetime(2026, 4, 15, 10, 0, tzinfo=AEST)
    mock_sync.get_all_lots.return_value = [
        _lot_on_date("ETH", 1.0, 3000.00, "2025-04-15T10:00:00+10:00", "t1"),
    ]
    mock_kraken.get_balances.return_value = {"ETH": Decimal("1.0")}
    mock_kraken.get_ticker_prices.return_value = {"ETH": Decimal("4000.00")}

    result = get_unrealised_cgt()

    lot = result.lots[0]
    assert lot.cgt_discount_eligible is False
    assert lot.days_until_discount_eligible == 1  # need 16/04/2026


@patch("backend.services.portfolio_service.now_aest")
@patch("backend.services.portfolio_service.kraken_service")
@patch("backend.services.portfolio_service.sync_service")
def test_cgt_15apr2025_checked_16apr2026_eligible(mock_sync, mock_kraken, mock_now):
    """Buy 15/04/2025, check 16/04/2026 → more than 12 months, eligible."""
    mock_now.return_value = datetime(2026, 4, 16, 10, 0, tzinfo=AEST)
    mock_sync.get_all_lots.return_value = [
        _lot_on_date("ETH", 1.0, 3000.00, "2025-04-15T10:00:00+10:00", "t1"),
    ]
    mock_kraken.get_balances.return_value = {"ETH": Decimal("1.0")}
    mock_kraken.get_ticker_prices.return_value = {"ETH": Decimal("4000.00")}

    result = get_unrealised_cgt()

    lot = result.lots[0]
    assert lot.cgt_discount_eligible is True
    assert lot.days_until_discount_eligible == 0


@patch("backend.services.portfolio_service.now_aest")
@patch("backend.services.portfolio_service.kraken_service")
@patch("backend.services.portfolio_service.sync_service")
def test_cgt_leap_year_29feb(mock_sync, mock_kraken, mock_now):
    """Buy 29/02/2024 (leap year), check 01/03/2025 → earliest_eligible = 01/03/2025, eligible."""
    mock_now.return_value = datetime(2025, 3, 1, 10, 0, tzinfo=AEST)
    mock_sync.get_all_lots.return_value = [
        _lot_on_date("ETH", 1.0, 3000.00, "2024-02-29T10:00:00+11:00", "t1"),
    ]
    mock_kraken.get_balances.return_value = {"ETH": Decimal("1.0")}
    mock_kraken.get_ticker_prices.return_value = {"ETH": Decimal("4000.00")}

    result = get_unrealised_cgt()

    lot = result.lots[0]
    # acquired 29/02/2024 + 1 year = 28/02/2025 (no 29 Feb in 2025) + 1 day = 01/03/2025
    assert lot.cgt_discount_eligible is True
    assert lot.days_until_discount_eligible == 0


@patch("backend.services.portfolio_service.now_aest")
@patch("backend.services.portfolio_service.kraken_service")
@patch("backend.services.portfolio_service.sync_service")
def test_cgt_leap_year_29feb_day_before(mock_sync, mock_kraken, mock_now):
    """Buy 29/02/2024, check 28/02/2025 → NOT eligible (exactly 12 months)."""
    mock_now.return_value = datetime(2025, 2, 28, 10, 0, tzinfo=AEST)
    mock_sync.get_all_lots.return_value = [
        _lot_on_date("ETH", 1.0, 3000.00, "2024-02-29T10:00:00+11:00", "t1"),
    ]
    mock_kraken.get_balances.return_value = {"ETH": Decimal("1.0")}
    mock_kraken.get_ticker_prices.return_value = {"ETH": Decimal("4000.00")}

    result = get_unrealised_cgt()

    lot = result.lots[0]
    assert lot.cgt_discount_eligible is False
    assert lot.days_until_discount_eligible == 1


@patch("backend.services.portfolio_service.now_aest")
@patch("backend.services.portfolio_service.kraken_service")
@patch("backend.services.portfolio_service.sync_service")
def test_cgt_nonleap_28feb(mock_sync, mock_kraken, mock_now):
    """Buy 28/02/2025 (non-leap), check 01/03/2026 → earliest_eligible = 01/03/2026, eligible."""
    mock_now.return_value = datetime(2026, 3, 1, 10, 0, tzinfo=AEST)
    mock_sync.get_all_lots.return_value = [
        _lot_on_date("ETH", 1.0, 3000.00, "2025-02-28T10:00:00+11:00", "t1"),
    ]
    mock_kraken.get_balances.return_value = {"ETH": Decimal("1.0")}
    mock_kraken.get_ticker_prices.return_value = {"ETH": Decimal("4000.00")}

    result = get_unrealised_cgt()

    lot = result.lots[0]
    # acquired 28/02/2025 + 1 year = 28/02/2026 + 1 day = 01/03/2026
    assert lot.cgt_discount_eligible is True
    assert lot.days_until_discount_eligible == 0


@patch("backend.services.portfolio_service.now_aest")
@patch("backend.services.portfolio_service.kraken_service")
@patch("backend.services.portfolio_service.sync_service")
def test_cgt_nonleap_28feb_day_before(mock_sync, mock_kraken, mock_now):
    """Buy 28/02/2025, check 28/02/2026 → NOT eligible."""
    mock_now.return_value = datetime(2026, 2, 28, 10, 0, tzinfo=AEST)
    mock_sync.get_all_lots.return_value = [
        _lot_on_date("ETH", 1.0, 3000.00, "2025-02-28T10:00:00+11:00", "t1"),
    ]
    mock_kraken.get_balances.return_value = {"ETH": Decimal("1.0")}
    mock_kraken.get_ticker_prices.return_value = {"ETH": Decimal("4000.00")}

    result = get_unrealised_cgt()

    lot = result.lots[0]
    assert lot.cgt_discount_eligible is False
    assert lot.days_until_discount_eligible == 1


@patch("backend.services.portfolio_service.now_aest")
@patch("backend.services.portfolio_service.kraken_service")
@patch("backend.services.portfolio_service.sync_service")
def test_cgt_summary_and_sort(mock_sync, mock_kraken, mock_now):
    """Multiple lots: verify sort order, summary totals, and within-30-days count."""
    mock_now.return_value = datetime(2026, 4, 20, 10, 0, tzinfo=AEST)
    mock_sync.get_all_lots.return_value = [
        _lot_on_date("ETH", 1.0, 3000.00, "2025-04-10T10:00:00+10:00", "t1"),  # ~375 days, eligible
        _lot_on_date("SOL", 10.0, 200.00, "2025-04-05T10:00:00+10:00", "t2"),   # ~380 days, eligible
        _lot_on_date("ADA", 500.0, 1.00, "2026-04-01T10:00:00+10:00", "t3"),    # ~19 days, not eligible
    ]
    mock_kraken.get_balances.return_value = {
        "ETH": Decimal("1.0"), "SOL": Decimal("10.0"), "ADA": Decimal("500.0")
    }
    mock_kraken.get_ticker_prices.return_value = {
        "ETH": Decimal("4000.00"), "SOL": Decimal("250.00"), "ADA": Decimal("1.20"),
    }

    result = get_unrealised_cgt()

    # Sorted by days_until ascending: eligible lots (0) first, then ADA
    assert result.lots[0].days_until_discount_eligible == 0
    assert result.lots[1].days_until_discount_eligible == 0
    assert result.lots[2].days_until_discount_eligible > 0

    # Eligible lots: ETH gained 1000, SOL gained 500
    assert result.summary.total_eligible_gain_aud == 1000.00 + 500.00
    # ADA: 500 * 1.20 - 500 * 1.00 = 100
    assert result.summary.total_ineligible_gain_aud == 100.00

    # ADA is not within 30 days of eligibility (still ~346 days away)
    assert result.summary.lots_within_30_days_of_eligibility == 0
