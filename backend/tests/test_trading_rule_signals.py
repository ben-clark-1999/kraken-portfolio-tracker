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
    # Old high of 200 sits outside the trailing window; recent high is 100.
    # 26 bars so that after the just-closed bar is excluded, the leading 200
    # still falls outside the trailing 24-bar window.
    closes = [Decimal("200")] + [Decimal("100")] * 25
    assert trend_signal(
        current_price=Decimal("102"), closes=closes,
        lookback_bars=24, min_move_pct=Decimal("1.5"),
    ) == "long"


def test_trend_long_when_just_closed_bar_is_the_breakout():
    # The most recent completed bar IS the breakout bar (100→110) and the live
    # mid equals its close. The trailing high must be measured over the bars
    # BEFORE it; otherwise the breakout hides inside its own window and the
    # signal is permanently "hold" (the live cron-at-bar-boundary bug).
    closes = [Decimal("100")] * 24 + [Decimal("110")]
    assert trend_signal(
        current_price=Decimal("110"), closes=closes,
        lookback_bars=24, min_move_pct=Decimal("1.5"),
    ) == "long"


def test_trend_exit_when_just_closed_bar_is_the_breakdown():
    # Symmetric: the most recent completed bar broke down (100→90) and the live
    # mid equals its close. The trailing low must exclude that bar.
    closes = [Decimal("100")] * 24 + [Decimal("90")]
    assert trend_signal(
        current_price=Decimal("90"), closes=closes,
        lookback_bars=24, min_move_pct=Decimal("1.5"),
    ) == "exit"


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
