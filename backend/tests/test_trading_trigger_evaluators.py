from decimal import Decimal
from datetime import datetime, timezone

from backend.services.trading.trigger_evaluators import (
    detect_breakout, detect_stretch, BarSeries,
)


def _bars(prices):
    return BarSeries([Decimal(p) for p in prices])


def test_breakout_up_when_close_exceeds_lookback_high_by_min_pct():
    bars = _bars(["100", "101", "102", "103", "104", "105"])
    # 1.5% above the lookback high of 105 = 106.575; current 107 → breakout
    evt = detect_breakout(
        pair="ETH/AUD", bars=bars, current_price=Decimal("107"),
        lookback_bars=5, min_move_pct=Decimal("1.5"),
        ts=datetime.now(timezone.utc),
    )
    assert evt is not None and evt.direction == "up"


def test_breakout_down_when_close_below_lookback_low_by_min_pct():
    bars = _bars(["100", "101", "102", "103", "104", "105"])
    # 1.5% below the lookback low of 100 = 98.5; current 98 → breakout down
    evt = detect_breakout(
        pair="ETH/AUD", bars=bars, current_price=Decimal("98"),
        lookback_bars=5, min_move_pct=Decimal("1.5"),
        ts=datetime.now(timezone.utc),
    )
    assert evt is not None and evt.direction == "down"


def test_no_breakout_when_within_band():
    bars = _bars(["100", "101", "102", "103", "104", "105"])
    evt = detect_breakout(
        pair="ETH/AUD", bars=bars, current_price=Decimal("105.5"),
        lookback_bars=5, min_move_pct=Decimal("1.5"),
        ts=datetime.now(timezone.utc),
    )
    assert evt is None


def test_stretch_fires_above_threshold_stdev():
    # Bars with mean ~100 and small stdev — current 110 is many stdev away.
    bars = _bars(["99", "100", "101", "100", "99", "100", "101"])
    evt = detect_stretch(
        pair="SOL/AUD", bars=bars, current_price=Decimal("110"),
        lookback_bars=7, stdev=Decimal("2"),
        ts=datetime.now(timezone.utc),
    )
    assert evt is not None and evt.direction == "above"


def test_stretch_does_not_fire_within_threshold():
    bars = _bars(["99", "100", "101", "100", "99", "100", "101"])
    evt = detect_stretch(
        pair="SOL/AUD", bars=bars, current_price=Decimal("100.5"),
        lookback_bars=7, stdev=Decimal("2"),
        ts=datetime.now(timezone.utc),
    )
    assert evt is None
