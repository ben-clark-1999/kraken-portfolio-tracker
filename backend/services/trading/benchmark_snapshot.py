"""Benchmark equity curves: BTC HODL and equal-weight alt basket.

Spec §4.7 + §8.3 — equal-weight basket REBALANCES monthly on the 1st
so that "lucky drift" doesn't make the benchmark unfairly hard to beat.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal


def compute_btc_hodl_equity(
    *, starting_balance_aud: Decimal,
    btc_price_at_start: Decimal, btc_price_now: Decimal,
) -> Decimal:
    if btc_price_at_start == 0:
        return Decimal("0")
    units = starting_balance_aud / btc_price_at_start
    return (units * btc_price_now).quantize(Decimal("0.0001"))


@dataclass
class AltBasketState:
    units: dict[str, Decimal] = field(default_factory=dict)
    last_rebalance_at: datetime | None = None

    @classmethod
    def initialise(
        cls, *, starting_balance_aud: Decimal,
        initial_prices: dict[str, Decimal], t0: datetime,
    ) -> "AltBasketState":
        per_asset = starting_balance_aud / Decimal(len(initial_prices))
        units = {pair: (per_asset / price) for pair, price in initial_prices.items()}
        return cls(units=units, last_rebalance_at=t0)

    def equity(self, *, current_prices: dict[str, Decimal]) -> Decimal:
        return sum(
            (self.units.get(p, Decimal("0")) * current_prices.get(p, Decimal("0"))
             for p in self.units),
            Decimal("0"),
        )

    def rebalance(self, *, current_prices: dict[str, Decimal],
                  now: datetime) -> None:
        eq = self.equity(current_prices=current_prices)
        per_asset = eq / Decimal(len(self.units))
        self.units = {p: (per_asset / current_prices[p]) for p in self.units}
        self.last_rebalance_at = now


def compute_alt_basket_equity(
    *, state: AltBasketState, current_prices: dict[str, Decimal],
) -> Decimal:
    return state.equity(current_prices=current_prices).quantize(Decimal("0.0001"))


def next_rebalance_due_at(last: datetime) -> datetime:
    # First of next month at 00:00 UTC.
    year, month = last.year, last.month
    if month == 12:
        year, month = year + 1, 1
    else:
        month += 1
    return datetime(year, month, 1, 0, 0, tzinfo=timezone.utc)
