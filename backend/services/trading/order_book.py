"""LocalOrderBook — in-process replica of Kraken's L2 book per pair.

Maintained from snapshot + diff messages on the Kraken WS `book` channel.
Kraken supplies a checksum on every update; on mismatch the maintainer
resubscribes for a fresh snapshot.

See docs/superpowers/specs/2026-05-12-paper-trading-sandbox-design.md §5.3.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Iterable

from backend.models.trading import OrderBookLevel


class ChecksumMismatch(Exception):
    """Raised when an applied diff's computed checksum != Kraken's expected."""


class LocalOrderBook:
    def __init__(self, pair: str) -> None:
        self.pair = pair
        self.asks: list[OrderBookLevel] = []   # ascending
        self.bids: list[OrderBookLevel] = []   # descending
        self.checksum: str = ""
        self.ts: datetime | None = None

    # ── snapshot / diff entry points ────────────────────────────

    def apply_snapshot(
        self,
        *,
        asks: list[OrderBookLevel],
        bids: list[OrderBookLevel],
        checksum: str,
        ts: datetime,
    ) -> None:
        self.asks = sorted(asks, key=lambda l: l.price)
        self.bids = sorted(bids, key=lambda l: l.price, reverse=True)
        self.checksum = checksum
        self.ts = ts

    def apply_diff(
        self,
        *,
        ask_updates: list[OrderBookLevel],
        bid_updates: list[OrderBookLevel],
        new_checksum: str | None,
        ts: datetime,
    ) -> None:
        self.asks = self._merge(self.asks, ask_updates, reverse=False)
        self.bids = self._merge(self.bids, bid_updates, reverse=True)
        self.ts = ts
        if new_checksum is not None:
            computed = self.compute_checksum()
            if computed != new_checksum:
                raise ChecksumMismatch(
                    f"{self.pair}: computed {computed}, expected {new_checksum}"
                )
            self.checksum = new_checksum

    # ── reads ───────────────────────────────────────────────────

    def top_ask(self) -> OrderBookLevel:
        return self.asks[0]

    def top_bid(self) -> OrderBookLevel:
        return self.bids[0]

    def mid(self) -> Decimal:
        return (self.top_ask().price + self.top_bid().price) / 2

    def age_seconds(self, now: datetime) -> float:
        if self.ts is None:
            return float("inf")
        return (now - self.ts).total_seconds()

    # ── internals ───────────────────────────────────────────────

    @staticmethod
    def _merge(
        existing: list[OrderBookLevel],
        updates: Iterable[OrderBookLevel],
        *,
        reverse: bool,
    ) -> list[OrderBookLevel]:
        by_price: dict[Decimal, Decimal] = {l.price: l.qty for l in existing}
        for u in updates:
            if u.qty == 0:
                by_price.pop(u.price, None)
            else:
                by_price[u.price] = u.qty
        merged = [OrderBookLevel(price=p, qty=q) for p, q in by_price.items()]
        merged.sort(key=lambda l: l.price, reverse=reverse)
        return merged

    def compute_checksum(self) -> str:
        """Match Kraken's L2 checksum algorithm.

        Kraken concatenates the top-10 price/qty (no decimal points, stripped
        leading zeros) ask-then-bid, then CRC32. See:
        https://docs.kraken.com/websockets/#book-checksum
        """
        import zlib

        def fmt(d: Decimal) -> str:
            # remove decimal point, strip leading zeros
            s = format(d.normalize(), "f").replace(".", "").lstrip("0")
            return s or "0"

        parts: list[str] = []
        for lvl in self.asks[:10]:
            parts.append(fmt(lvl.price))
            parts.append(fmt(lvl.qty))
        for lvl in self.bids[:10]:
            parts.append(fmt(lvl.price))
            parts.append(fmt(lvl.qty))
        return str(zlib.crc32("".join(parts).encode("ascii")))
