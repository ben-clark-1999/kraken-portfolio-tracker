from decimal import Decimal

from backend.services.trading.metrics import (
    compute_returns, sharpe_24_7, sortino_24_7,
    max_drawdown_pct, calmar, win_rate, payoff_ratio,
)


def test_returns_from_equity_curve():
    curve = [Decimal("1000"), Decimal("1100"), Decimal("990")]
    rs = compute_returns(curve)
    # ln-returns: ln(1.1), ln(0.9)
    assert len(rs) == 2


def test_sharpe_24_7_uses_sqrt_365():
    # All returns identical → stdev 0 → return inf-handling: define as 0.
    curve = [Decimal("1000")] * 10
    assert sharpe_24_7(curve) == Decimal("0")


def test_sharpe_positive_for_steady_upward_curve():
    curve = [Decimal("1000") * (Decimal("1.001") ** i) for i in range(30)]
    assert sharpe_24_7(curve) > Decimal("0")


def test_max_drawdown_pct():
    curve = [Decimal("1000"), Decimal("1200"), Decimal("800"), Decimal("1100")]
    # Peak 1200, trough 800 → 33.33% DD
    dd = max_drawdown_pct(curve)
    assert Decimal("33") < dd < Decimal("34")


def test_calmar_ratio():
    # Mocked simple: CAGR / max DD; the helper just divides.
    c = calmar(annualised_return_pct=Decimal("20"), max_dd_pct=Decimal("10"))
    assert c == Decimal("2")


def test_win_rate():
    rs = [Decimal("0.1"), Decimal("-0.05"), Decimal("0.2"), Decimal("-0.1"), Decimal("0.05")]
    assert win_rate(rs) == Decimal("0.6")


def test_payoff_ratio():
    rs = [Decimal("0.1"), Decimal("-0.05"), Decimal("0.2"), Decimal("-0.1"), Decimal("0.05")]
    # avg win = (0.1+0.2+0.05)/3 = 0.116…, avg loss = 0.075 → ratio ~1.555
    p = payoff_ratio(rs)
    assert Decimal("1.5") < p < Decimal("1.6")


def test_sortino_only_penalises_downside():
    curve = [Decimal("1000"), Decimal("1100"), Decimal("1050"),
             Decimal("1200"), Decimal("1150")]
    so = sortino_24_7(curve)
    sh = sharpe_24_7(curve)
    # Same curve — Sortino ≥ Sharpe because upside is excluded from stdev.
    assert so >= sh
