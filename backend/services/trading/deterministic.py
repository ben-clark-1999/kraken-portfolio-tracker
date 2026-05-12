"""Deterministic rebalance: compute the orders needed to align actual to target.

Used by DCA-Baseline (spec §6.4). Skips orders below an absolute AUD threshold
to avoid dust trades.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


REBALANCE_DUST_THRESHOLD_AUD = Decimal("0.50")


@dataclass
class TargetOrder:
    pair: str
    side: Literal["buy", "sell"]
    notional_aud: Decimal


def compute_rebalance_orders(
    *,
    positions_aud: dict[str, Decimal],   # 'AUD' + base assets (e.g. 'ETH')
    target_weights: dict[str, Decimal],  # pair → weight (sums to 1)
    starting_balance_aud: Decimal,
    mids: dict[str, Decimal],            # pair → current mid price (informational)
) -> list[TargetOrder]:
    # Equity is cash + every base asset's notional value in AUD.
    equity = sum(positions_aud.values(), Decimal("0"))
    orders: list[TargetOrder] = []
    for pair, target_weight in target_weights.items():
        asset = pair.split("/", 1)[0]
        actual = positions_aud.get(asset, Decimal("0"))
        target = equity * target_weight
        delta = target - actual
        if abs(delta) < REBALANCE_DUST_THRESHOLD_AUD:
            continue
        if delta > 0:
            orders.append(TargetOrder(pair=pair, side="buy", notional_aud=delta))
        else:
            orders.append(TargetOrder(pair=pair, side="sell", notional_aud=-delta))
    return orders
