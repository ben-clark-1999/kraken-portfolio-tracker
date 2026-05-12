"""Pure functions that classify market events into TriggerEvents.

Owners (spec §6.2):
- price_breakout / price_stretch → price_feed_task (Task 16)
- cron / interval → trigger_scheduler (Task 17)
- order_filled → PaperExecutor (already wired)
- drawdown → equity_snapshot (Task 25)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from statistics import mean, pstdev

from backend.models.trading import (
    PriceBreakoutEvent, PriceStretchEvent,
)


@dataclass
class BarSeries:
    closes: list[Decimal]


def detect_breakout(
    *,
    pair: str,
    bars: BarSeries,
    current_price: Decimal,
    lookback_bars: int,
    min_move_pct: Decimal,
    ts: datetime,
) -> PriceBreakoutEvent | None:
    window = bars.closes[-lookback_bars:]
    if not window:
        return None
    hi, lo = max(window), min(window)
    up_thresh = hi * (Decimal("1") + min_move_pct / Decimal("100"))
    dn_thresh = lo * (Decimal("1") - min_move_pct / Decimal("100"))
    if current_price >= up_thresh:
        move_pct = (current_price - hi) / hi * Decimal("100")
        return PriceBreakoutEvent(
            pair=pair, direction="up", move_pct=move_pct,
            lookback_bars=lookback_bars, ts=ts,
        )
    if current_price <= dn_thresh:
        move_pct = (lo - current_price) / lo * Decimal("100")
        return PriceBreakoutEvent(
            pair=pair, direction="down", move_pct=move_pct,
            lookback_bars=lookback_bars, ts=ts,
        )
    return None


def detect_stretch(
    *,
    pair: str,
    bars: BarSeries,
    current_price: Decimal,
    lookback_bars: int,
    stdev: Decimal,
    ts: datetime,
) -> PriceStretchEvent | None:
    window = [float(c) for c in bars.closes[-lookback_bars:]]
    if len(window) < 2:
        return None
    mu = Decimal(str(mean(window)))
    sigma = Decimal(str(pstdev(window)))
    if sigma == 0:
        return None
    z = (current_price - mu) / sigma
    if z >= stdev:
        return PriceStretchEvent(pair=pair, direction="above",
                                 stdev_distance=z, ts=ts)
    if z <= -stdev:
        return PriceStretchEvent(pair=pair, direction="below",
                                 stdev_distance=-z, ts=ts)
    return None
