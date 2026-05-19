"""Fee schedule and per-fill fee calculation.

See spec §5.4. Lowest 30-day USD volume tier on Kraken Pro spot:
0.40% maker / 0.80% taker (verified against kraken.com/features/fee-schedule
2026-05-19).

These numbers materially affect strategy attribution — the whole point of
running paper-trading is to compare alternative methods against DCA, and an
under-stated fee schedule biases the result in favour of churn-heavy
strategies. Round-trip taker is 1.6%, which eats most of a typical
mean-reversion edge; the personas reference these numbers so the LLM can
weigh trade EV honestly.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


@dataclass(frozen=True)
class FeeSchedule:
    maker_bps: int   # basis points; 1 bp = 0.01%
    taker_bps: int


KRAKEN_PRO_SPOT_TIER_1 = FeeSchedule(maker_bps=40, taker_bps=80)


def apply_fee(
    *,
    qty: Decimal,
    price: Decimal,
    role: Literal["maker", "taker"],
    schedule: FeeSchedule = KRAKEN_PRO_SPOT_TIER_1,
) -> Decimal:
    bps = schedule.maker_bps if role == "maker" else schedule.taker_bps
    return qty * price * Decimal(bps) / Decimal(10_000)
