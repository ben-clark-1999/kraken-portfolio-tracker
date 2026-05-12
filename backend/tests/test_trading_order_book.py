from decimal import Decimal
from datetime import datetime, timezone

import pytest

from backend.models.trading import OrderBookLevel
from backend.services.trading.order_book import LocalOrderBook, ChecksumMismatch


def _ts():
    return datetime.now(timezone.utc)


def test_apply_snapshot_replaces_state():
    ob = LocalOrderBook("ETH/AUD")
    ob.apply_snapshot(
        asks=[OrderBookLevel(price=Decimal("100"), qty=Decimal("1"))],
        bids=[OrderBookLevel(price=Decimal("99"), qty=Decimal("2"))],
        checksum="snap1",
        ts=_ts(),
    )
    assert ob.top_ask().price == Decimal("100")
    assert ob.top_bid().price == Decimal("99")


def test_apply_diff_updates_level_qty():
    ob = LocalOrderBook("ETH/AUD")
    ob.apply_snapshot(
        asks=[OrderBookLevel(price=Decimal("100"), qty=Decimal("1"))],
        bids=[OrderBookLevel(price=Decimal("99"), qty=Decimal("2"))],
        checksum="snap1", ts=_ts(),
    )
    ob.apply_diff(
        ask_updates=[OrderBookLevel(price=Decimal("100"), qty=Decimal("3"))],
        bid_updates=[],
        new_checksum=None, ts=_ts(),
    )
    assert ob.asks[0].qty == Decimal("3")


def test_apply_diff_qty_zero_removes_level():
    ob = LocalOrderBook("ETH/AUD")
    ob.apply_snapshot(
        asks=[
            OrderBookLevel(price=Decimal("100"), qty=Decimal("1")),
            OrderBookLevel(price=Decimal("101"), qty=Decimal("2")),
        ],
        bids=[], checksum="snap1", ts=_ts(),
    )
    ob.apply_diff(
        ask_updates=[OrderBookLevel(price=Decimal("100"), qty=Decimal("0"))],
        bid_updates=[], new_checksum=None, ts=_ts(),
    )
    assert len(ob.asks) == 1
    assert ob.asks[0].price == Decimal("101")


def test_apply_diff_insert_new_level_in_sort_order():
    ob = LocalOrderBook("ETH/AUD")
    ob.apply_snapshot(
        asks=[
            OrderBookLevel(price=Decimal("100"), qty=Decimal("1")),
            OrderBookLevel(price=Decimal("102"), qty=Decimal("1")),
        ],
        bids=[], checksum="snap1", ts=_ts(),
    )
    ob.apply_diff(
        ask_updates=[OrderBookLevel(price=Decimal("101"), qty=Decimal("5"))],
        bid_updates=[], new_checksum=None, ts=_ts(),
    )
    assert [a.price for a in ob.asks] == [Decimal("100"), Decimal("101"), Decimal("102")]


def test_checksum_mismatch_raises():
    ob = LocalOrderBook("ETH/AUD")
    ob.apply_snapshot(
        asks=[OrderBookLevel(price=Decimal("100"), qty=Decimal("1"))],
        bids=[OrderBookLevel(price=Decimal("99"), qty=Decimal("1"))],
        checksum="snap1", ts=_ts(),
    )
    with pytest.raises(ChecksumMismatch):
        ob.apply_diff(
            ask_updates=[], bid_updates=[],
            new_checksum="not_the_checksum_we_compute", ts=_ts(),
        )


def test_age_seconds_grows_with_time():
    ob = LocalOrderBook("ETH/AUD")
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ob.apply_snapshot(
        asks=[OrderBookLevel(price=Decimal("100"), qty=Decimal("1"))],
        bids=[OrderBookLevel(price=Decimal("99"), qty=Decimal("1"))],
        checksum="x", ts=old,
    )
    # at "now" the age should be large
    assert ob.age_seconds(_ts()) > 60 * 60 * 24  # >1 day
