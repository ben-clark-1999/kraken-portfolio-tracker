from decimal import Decimal

from backend.services.trading.deterministic import (
    trend_signal, mean_reversion_signal,
)


# ── trend_signal: trailing 24h high/low breakout ──────────────────
def test_trend_long_on_breakout_above_high():
    closes = [Decimal("100")] * 24
    # 1.5% above the trailing high (100 → 101.5) triggers long.
    assert trend_signal(
        current_price=Decimal("102"), closes=closes,
        lookback_bars=24, min_move_pct=Decimal("1.5"),
    ) == "long"


def test_trend_exit_on_breakdown_below_low():
    closes = [Decimal("100")] * 24
    assert trend_signal(
        current_price=Decimal("98"), closes=closes,
        lookback_bars=24, min_move_pct=Decimal("1.5"),
    ) == "exit"


def test_trend_hold_within_band():
    closes = [Decimal("100")] * 24
    assert trend_signal(
        current_price=Decimal("100.5"), closes=closes,
        lookback_bars=24, min_move_pct=Decimal("1.5"),
    ) == "hold"


def test_trend_uses_only_lookback_window():
    # Old high of 200 sits outside the 24-bar window; recent high is 100.
    closes = [Decimal("200")] + [Decimal("100")] * 24
    assert trend_signal(
        current_price=Decimal("102"), closes=closes,
        lookback_bars=24, min_move_pct=Decimal("1.5"),
    ) == "long"


# ── mean_reversion_signal: 48h z-score ────────────────────────────
def test_mean_reversion_buy_at_or_below_minus_two_sigma():
    assert mean_reversion_signal(
        z=Decimal("-2.1"), entry_z=Decimal("-2"), exit_z=Decimal("0"),
    ) == "buy"


def test_mean_reversion_exit_at_or_above_mean():
    assert mean_reversion_signal(
        z=Decimal("0.1"), entry_z=Decimal("-2"), exit_z=Decimal("0"),
    ) == "exit"


def test_mean_reversion_hold_between_thresholds():
    assert mean_reversion_signal(
        z=Decimal("-1.0"), entry_z=Decimal("-2"), exit_z=Decimal("0"),
    ) == "hold"
