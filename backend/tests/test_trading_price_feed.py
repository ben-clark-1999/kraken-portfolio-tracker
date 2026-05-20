import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from backend.services.trading.event_bus import EventBus
from backend.services.trading.price_feed import (
    PriceFeed, parse_book_snapshot_message, parse_book_update_message,
    parse_trade_message, kraken_pair_to_canonical,
)


def test_kraken_pair_to_canonical():
    assert kraken_pair_to_canonical("ETH/AUD") == "ETH/AUD"
    assert kraken_pair_to_canonical("XETHZAUD") == "ETH/AUD"


def test_parse_book_snapshot():
    # Kraken WS shape (v2):
    msg = {
        "channel": "book",
        "type": "snapshot",
        "data": [
            {
                "symbol": "ETH/AUD",
                "bids": [{"price": 100.0, "qty": 1.0}, {"price": 99.0, "qty": 2.0}],
                "asks": [{"price": 101.0, "qty": 0.5}, {"price": 102.0, "qty": 1.5}],
                "checksum": 1234567,
                "timestamp": "2026-05-12T00:00:00Z",
            }
        ],
    }
    snap = parse_book_snapshot_message(msg)
    assert snap.pair == "ETH/AUD"
    assert len(snap.asks) == 2 and len(snap.bids) == 2
    assert snap.checksum == "1234567"


def test_parse_book_update():
    msg = {
        "channel": "book",
        "type": "update",
        "data": [
            {
                "symbol": "ETH/AUD",
                "bids": [{"price": 99.5, "qty": 0.0}],
                "asks": [{"price": 101.0, "qty": 0.75}],
                "checksum": 7654321,
                "timestamp": "2026-05-12T00:00:01Z",
            }
        ],
    }
    parsed = parse_book_update_message(msg)
    assert parsed.pair == "ETH/AUD"
    assert parsed.checksum == "7654321"


def test_parse_trade_message_extracts_last_price():
    msg = {
        "channel": "trade",
        "data": [
            {"symbol": "ETH/AUD", "side": "buy", "price": 3196.6,
             "qty": 0.1, "timestamp": "2026-05-12T00:00:02Z",
             "trade_id": 123},
        ],
    }
    tick = parse_trade_message(msg)
    assert tick.pair == "ETH/AUD"
    assert tick.price == Decimal("3196.6")


def test_is_ws_healthy_before_any_message_is_false():
    feed = PriceFeed(pairs=["ETH/AUD"], bus=EventBus())
    now = datetime.now(timezone.utc)
    assert feed.is_ws_healthy(now) is False


def test_is_ws_healthy_after_recent_message_is_true():
    feed = PriceFeed(pairs=["ETH/AUD"], bus=EventBus())
    now = datetime.now(timezone.utc)
    feed.last_message_at = now - timedelta(seconds=2)
    assert feed.is_ws_healthy(now) is True


def test_is_ws_healthy_after_stale_message_is_false():
    feed = PriceFeed(pairs=["ETH/AUD"], bus=EventBus())
    now = datetime.now(timezone.utc)
    feed.last_message_at = now - timedelta(seconds=15)
    assert feed.is_ws_healthy(now) is False


def test_heartbeat_message_refreshes_health_without_affecting_books():
    feed = PriceFeed(pairs=["ETH/AUD"], bus=EventBus())
    assert feed.last_message_at is None
    asyncio.run(feed._handle({"channel": "heartbeat"}))
    assert feed.last_message_at is not None
    # The heartbeat path must not touch the per-pair book.
    assert feed.books["ETH/AUD"].ts is None
