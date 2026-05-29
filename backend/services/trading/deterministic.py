"""Deterministic rebalance: compute the orders needed to align actual to target.

Used by DCA-Baseline (spec §6.4). Skips orders below an absolute AUD threshold
to avoid dust trades.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
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


def split_order(*, order: TargetOrder, max_order_aud: Decimal) -> list[TargetOrder]:
    """Split a target order into N equal ≤-cap chunks (spec §3.7).

    Targets that exceed the uniform per-order cap are reached via multiple
    orders rather than being rejected. Chunks are equal so the sum is exactly
    the original notional (no rounding drift).
    """
    if order.notional_aud <= max_order_aud:
        return [order]
    n = int((order.notional_aud / max_order_aud).to_integral_value(rounding=ROUND_CEILING))
    chunk = order.notional_aud / Decimal(n)
    # n-1 equal chunks, with the final chunk absorbing any Decimal-division
    # residual so the chunks sum *exactly* to the original notional (e.g.
    # 700/3 would otherwise drift to 699.999…). chunk = total/n ≤ cap, and the
    # residual is sub-cent, so the final chunk stays under the cap too.
    out = [
        TargetOrder(pair=order.pair, side=order.side, notional_aud=chunk)
        for _ in range(n - 1)
    ]
    spent = chunk * Decimal(n - 1)
    out.append(TargetOrder(
        pair=order.pair, side=order.side,
        notional_aud=order.notional_aud - spent,
    ))
    return out


# A fire that would spend less than this is treated as cash-exhausted; the
# strategy holds rather than emitting dust orders (spec §3.1 stop condition).
DCA_MIN_SPEND_AUD = Decimal("1.00")


def compute_dca_orders(
    *, cash_aud: Decimal, slice_total: Decimal, weights: dict[str, Decimal],
) -> list[TargetOrder]:
    """Fixed-slice dollar-cost averaging (spec §3.1).

    Spend one slice (or whatever cash remains, if less) split across pairs by
    weight. Below the dust floor, return no orders — the strategy is fully
    invested and now holds. A skipped week (feed down) just delays completion:
    the slice comes from remaining cash on the next successful fire, so no
    money is lost or double-spent.
    """
    spend = min(slice_total, cash_aud)
    if spend < DCA_MIN_SPEND_AUD:
        return []
    # Pairs whose slice share clears the dust floor; sub-dust shares stay as
    # cash (we don't force-spend them onto other pairs).
    kept = [(p, w) for p, w in weights.items()
            if spend * w >= REBALANCE_DUST_THRESHOLD_AUD]
    if not kept:
        return []
    total_w = sum((w for _, w in kept), Decimal("0"))
    orders: list[TargetOrder] = []
    allocated = Decimal("0")
    for i, (pair, weight) in enumerate(kept):
        if i == len(kept) - 1:
            # Final order absorbs the Decimal-division residual so the kept
            # orders sum exactly to spend*total_w (no rounding drift).
            notional = spend * total_w - allocated
        else:
            notional = spend * weight
            allocated += notional
        orders.append(TargetOrder(pair=pair, side="buy", notional_aud=notional))
    return orders
