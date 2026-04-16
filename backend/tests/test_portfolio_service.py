from decimal import Decimal
from backend.services.portfolio_service import calculate_summary, get_dca_history, calculate_next_dca_date
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
