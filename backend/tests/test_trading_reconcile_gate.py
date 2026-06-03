"""Regression: the price feed must only reconcile pairs that actually have a
resting limit order. Reconciling every pair on every book tick floods the DB
with synchronous Supabase queries and starves the asyncio event loop (the HTTP
server stops responding). See the reconcile wiring added for spec §3.2.
"""
from datetime import datetime, timezone

import pytest

from backend.services.trading.price_feed import PriceFeed


class _SpyExecutor:
    def __init__(self):
        self._books = {}
        self._resting_pairs: set[str] = set()
        self.reconcile_calls: list[str] = []

    def attach_book(self, pair, book):
        self._books[pair] = book

    async def reconcile_resting_orders(self, pair):
        self.reconcile_calls.append(pair)


def _book_msg(pair: str) -> dict:
    return {"channel": "book", "type": "snapshot", "data": [{
        "symbol": pair,
        "asks": [{"price": "3100", "qty": "1"}],
        "bids": [{"price": "3090", "qty": "1"}],
        "checksum": "1", "timestamp": datetime.now(timezone.utc).isoformat()}]}


@pytest.mark.asyncio
async def test_no_reconcile_when_no_resting_orders():
    ex = _SpyExecutor()
    feed = PriceFeed(pairs=["ETH/AUD"], executor=ex)
    await feed._handle(_book_msg("ETH/AUD"))
    # Nothing resting → no per-tick DB reconcile (avoids event-loop starvation).
    assert ex.reconcile_calls == []


@pytest.mark.asyncio
async def test_reconcile_when_pair_has_resting_order():
    ex = _SpyExecutor()
    feed = PriceFeed(pairs=["ETH/AUD"], executor=ex)
    ex._resting_pairs.add("ETH/AUD")
    await feed._handle(_book_msg("ETH/AUD"))
    assert ex.reconcile_calls == ["ETH/AUD"]
