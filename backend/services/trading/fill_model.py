"""Walk-the-book fill simulation.

Used by PaperExecutor (spec §5.2 / §5.3). Market orders walk the opposite
side of the book consuming liquidity at progressively worse prices. An
aggressive (crossing) limit is treated as a partial walk capped at the
limit price; a passive limit returns no immediate fills and rests on
the book until reconciled.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal

from backend.models.trading import Fill
from backend.services.trading.fees import KRAKEN_PRO_SPOT_TIER_1, apply_fee
from backend.services.trading.order_book import LocalOrderBook


class InsufficientDepth(Exception):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _walk(
    *,
    levels,
    qty: Decimal,
    fee_role: Literal["maker", "taker"],
    book_state_hash: str,
    price_cap: Decimal | None,
    cap_direction: Literal["max", "min"] | None,
) -> list[Fill]:
    """Walk `levels` in their given order; stop on price-cap violation."""
    remaining = qty
    fills: list[Fill] = []
    for lvl in levels:
        if price_cap is not None:
            if cap_direction == "max" and lvl.price > price_cap:
                break
            if cap_direction == "min" and lvl.price < price_cap:
                break
        take = min(lvl.qty, remaining)
        if take <= 0:
            continue
        fee = apply_fee(qty=take, price=lvl.price, role=fee_role,
                        schedule=KRAKEN_PRO_SPOT_TIER_1)
        fills.append(Fill(
            qty=take, price=lvl.price, fee_aud=fee,
            fee_role=fee_role, book_state_hash=book_state_hash,
            filled_at=_now(),
        ))
        remaining -= take
        if remaining == 0:
            break
    if price_cap is None and remaining > 0:
        raise InsufficientDepth(f"{remaining} qty unfilled")
    return fills


def walk_book_for_market(
    *,
    book: LocalOrderBook,
    side: Literal["buy", "sell"],
    qty: Decimal,
) -> list[Fill]:
    levels = book.asks if side == "buy" else book.bids
    return _walk(
        levels=levels, qty=qty, fee_role="taker",
        book_state_hash=book.checksum,
        price_cap=None, cap_direction=None,
    )


def walk_book_for_limit(
    *,
    book: LocalOrderBook,
    side: Literal["buy", "sell"],
    qty: Decimal,
    limit_price: Decimal,
) -> list[Fill]:
    """Returns immediate fills if the limit crosses the book; [] if it rests."""
    if side == "buy":
        # Only fill against asks priced ≤ limit_price; charge TAKER (we crossed).
        if not book.asks or book.asks[0].price > limit_price:
            return []
        return _walk(
            levels=book.asks, qty=qty, fee_role="taker",
            book_state_hash=book.checksum,
            price_cap=limit_price, cap_direction="max",
        )
    else:
        if not book.bids or book.bids[0].price < limit_price:
            return []
        return _walk(
            levels=book.bids, qty=qty, fee_role="taker",
            book_state_hash=book.checksum,
            price_cap=limit_price, cap_direction="min",
        )
