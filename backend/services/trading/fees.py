"""Fee schedule and per-fill fee calculation.

See spec §5.4. Lowest 30-day USD volume tier on Kraken Pro spot:
0.25% maker / 0.40% taker.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class FeeSchedule:
    maker_bps: int   # basis points; 1 bp = 0.01%
    taker_bps: int


# Spec decision-log row 13 — verified against kraken.com/features/fee-schedule.
KRAKEN_PRO_SPOT_TIER_1 = FeeSchedule(maker_bps=25, taker_bps=40)


def apply_fee(
    *,
    qty: Decimal,
    price: Decimal,
    role: Literal["maker", "taker"],
    schedule: FeeSchedule = KRAKEN_PRO_SPOT_TIER_1,
) -> Decimal:
    bps = schedule.maker_bps if role == "maker" else schedule.taker_bps
    return qty * price * Decimal(bps) / Decimal(10_000)
