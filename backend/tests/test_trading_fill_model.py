from decimal import Decimal
from datetime import datetime, timezone

import pytest

from backend.models.trading import OrderBookLevel
from backend.services.trading.order_book import LocalOrderBook
from backend.services.trading.fill_model import (
    walk_book_for_market, walk_book_for_limit, InsufficientDepth,
)


def _book_with(asks, bids):
    ob = LocalOrderBook("ETH/AUD")
    ob.apply_snapshot(
        asks=[OrderBookLevel(price=Decimal(p), qty=Decimal(q)) for p, q in asks],
        bids=[OrderBookLevel(price=Decimal(p), qty=Decimal(q)) for p, q in bids],
        checksum="x",
        ts=datetime.now(timezone.utc),
    )
    return ob


def test_market_buy_walks_asks_in_ascending_order():
    ob = _book_with(
        asks=[("100", "0.5"), ("101", "1.0"), ("102", "2.0")],
        bids=[("99", "1")],
    )
    fills = walk_book_for_market(book=ob, side="buy", qty=Decimal("1.2"))
    # 0.5 @ 100 + 0.7 @ 101 = 1.2
    assert len(fills) == 2
    assert fills[0].price == Decimal("100") and fills[0].qty == Decimal("0.5")
    assert fills[1].price == Decimal("101") and fills[1].qty == Decimal("0.7")
    for f in fills:
        assert f.fee_role == "taker"


def test_market_sell_walks_bids_descending():
    ob = _book_with(
        asks=[("100", "1")],
        bids=[("99", "0.5"), ("98", "1.0")],
    )
    fills = walk_book_for_market(book=ob, side="sell", qty=Decimal("0.8"))
    assert fills[0].price == Decimal("99") and fills[0].qty == Decimal("0.5")
    assert fills[1].price == Decimal("98") and fills[1].qty == Decimal("0.3")


def test_market_qty_fits_first_level_one_fill():
    ob = _book_with(asks=[("100", "2")], bids=[("99", "1")])
    fills = walk_book_for_market(book=ob, side="buy", qty=Decimal("1"))
    assert len(fills) == 1
    assert fills[0].qty == Decimal("1")


def test_market_insufficient_depth_raises():
    ob = _book_with(asks=[("100", "0.5")], bids=[("99", "1")])
    with pytest.raises(InsufficientDepth):
        walk_book_for_market(book=ob, side="buy", qty=Decimal("10"))


def test_limit_buy_resting_when_above_best_ask_fills_immediately_at_limit():
    """Aggressive limit that crosses the book is a maker-no-more: it fills now.

    Convention used by PaperExecutor: an aggressive (crossing) limit is
    classified as TAKER and walks the book just like a market — but caps at
    the limit price.
    """
    ob = _book_with(asks=[("100", "1"), ("101", "1")], bids=[("99", "1")])
    fills = walk_book_for_limit(
        book=ob, side="buy", qty=Decimal("1.5"), limit_price=Decimal("100.50"),
    )
    # Only 1.0 of the 100 level qualifies (101 > 100.50).
    assert len(fills) == 1
    assert fills[0].price == Decimal("100")
    assert fills[0].qty == Decimal("1")
    assert fills[0].fee_role == "taker"


def test_limit_buy_below_best_ask_does_not_fill():
    ob = _book_with(asks=[("100", "1")], bids=[("99", "1")])
    fills = walk_book_for_limit(
        book=ob, side="buy", qty=Decimal("1"), limit_price=Decimal("99.50"),
    )
    assert fills == []   # rests on the book, no immediate fill
