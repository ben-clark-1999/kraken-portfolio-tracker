"""Pure-function TWR tests. No DB, no HTTP.

In real production data, cash flows happen BETWEEN hourly snapshots,
not at the same timestamp. These tests reflect that: the snapshot
times and cash-flow times are distinct, and compute_twr must merge
them chronologically and segment internally.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.services.manual_performance import (
    CashFlowEvent, EquityPoint, compute_twr,
)


def _ep(days_ago: int, value: str) -> EquityPoint:
    return EquityPoint(
        captured_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        total_value_aud=Decimal(value),
    )


def _cf(days_ago: int, amount: str, kind: str = "deposit") -> CashFlowEvent:
    return CashFlowEvent(
        occurred_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        amount_aud=Decimal(amount),
        kind=kind,
    )


def test_no_cash_flow_single_segment():
    curve = [_ep(7, "1000"), _ep(0, "1100")]
    twr, unit_curve = compute_twr(curve, cash_flows=[])
    assert twr == Decimal("10.00")  # +10%
    assert unit_curve == [Decimal("1"), Decimal("1.1")]


def test_one_deposit_mid_window():
    # Day-7: snap $1000. Day-3: snap $1100 (just before deposit).
    # Day-2: deposit $500 (1 day after the day-3 snapshot).
    # Day-0: snap $1600 (no market movement; 1100+500=1600).
    #
    # Segment 1 (day-7 → day-2 deposit): 1100/1000 = 1.10
    # Segment 2 (day-2 → day-0): 1600/(1100+500) = 1.00
    # TWR = 1.10 * 1.00 - 1 = +10%.
    curve = [_ep(7, "1000"), _ep(3, "1100"), _ep(0, "1600")]
    cf = _cf(2, "500", kind="deposit")
    twr, _ = compute_twr(curve, cash_flows=[cf])
    assert twr == Decimal("10.00")


def test_one_withdrawal_mid_window():
    # Day-7: $1000. Day-3: $1100. Day-2: withdraw 300.
    # Day-0: $800 (= 1100 - 300, no movement).
    # Segment 1: 1100/1000 = 1.10. Segment 2: 800/(1100-300) = 1.00. TWR = +10%.
    curve = [_ep(7, "1000"), _ep(3, "1100"), _ep(0, "800")]
    cf = _cf(2, "300", kind="withdrawal")
    twr, _ = compute_twr(curve, cash_flows=[cf])
    assert twr == Decimal("10.00")


def test_synthetic_unit_curve_grows_segment_by_segment():
    # Day-7: $1000. Day-3: $1100. Day-2: deposit $500. Day-0: $1696.
    # Seg1: 1100/1000 = 1.10. Seg2: 1696/1600 = 1.06.
    # Compound: 1.10 * 1.06 - 1 = 0.166 → 16.60%.
    curve = [_ep(7, "1000"), _ep(3, "1100"), _ep(0, "1696")]
    cf = _cf(2, "500", kind="deposit")
    twr, unit_curve = compute_twr(curve, cash_flows=[cf])
    assert twr == Decimal("16.60")
    # One unit-curve point per snapshot. Cash flow doesn't add a point.
    assert len(unit_curve) == 3
    assert unit_curve[0] == Decimal("1")
    assert unit_curve[-1] == Decimal("1.166")


def test_multiple_cash_flows_in_sequence():
    # Day-10: $1000. Day-7: $1050 (+5%). Day-6: deposit $500.
    # Day-3: $1550 (no movement; 1050+500). Day-2: withdraw $100.
    # Day-0: $1595 (1450 * 1.10 = 1595).
    # Seg1: 1050/1000 = 1.05. Seg2: 1550/1550 = 1.00. Seg3: 1595/1450 = 1.10.
    # Compound: 1.05 * 1.00 * 1.10 - 1 = 0.155 → 15.50%.
    curve = [_ep(10, "1000"), _ep(7, "1050"), _ep(3, "1550"), _ep(0, "1595")]
    cfs = [_cf(6, "500", "deposit"), _cf(2, "100", "withdrawal")]
    twr, _ = compute_twr(curve, cash_flows=cfs)
    assert twr == Decimal("15.50")


def test_empty_curve_returns_zero_pct():
    twr, unit_curve = compute_twr([], cash_flows=[])
    assert twr == Decimal("0")
    assert unit_curve == [Decimal("1")]


def test_zero_portfolio_mid_window_locks_at_minus_100():
    # Day-7: $1000. Day-3: $0 (sold everything). Day-0: still $0.
    curve = [_ep(7, "1000"), _ep(3, "0"), _ep(0, "0")]
    twr, unit_curve = compute_twr(curve, cash_flows=[])
    assert twr == Decimal("-100.00")
    assert unit_curve[-1] == Decimal("0")


def test_cash_flow_before_first_snapshot_is_ignored():
    # Cash flow at day-10, first snapshot at day-7. No baseline before the
    # snapshot, so the cash flow is silently dropped.
    curve = [_ep(7, "1000"), _ep(0, "1100")]
    cf = _cf(10, "500", "deposit")
    twr, _ = compute_twr(curve, cash_flows=[cf])
    assert twr == Decimal("10.00")
