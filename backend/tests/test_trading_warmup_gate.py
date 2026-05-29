import asyncio
from decimal import Decimal

import pytest

from backend.services.trading.price_feed import wait_for_books


class _Book:
    def __init__(self): self.asks = []; self.bids = []


class _Ex:
    def __init__(self): self._books = {"ETH/AUD": _Book(), "SOL/AUD": _Book()}


@pytest.mark.asyncio
async def test_returns_true_once_all_books_populate():
    ex = _Ex()

    async def _populate():
        await asyncio.sleep(0.05)
        for b in ex._books.values():
            b.asks = [object()]; b.bids = [object()]

    asyncio.create_task(_populate())
    ok = await wait_for_books(ex, ["ETH/AUD", "SOL/AUD"], timeout_s=2.0, poll_s=0.01)
    assert ok is True


@pytest.mark.asyncio
async def test_returns_false_on_timeout_when_books_stay_empty():
    ex = _Ex()
    ok = await wait_for_books(ex, ["ETH/AUD"], timeout_s=0.1, poll_s=0.01)
    assert ok is False
