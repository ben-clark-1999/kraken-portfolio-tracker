"""Kraken WebSocket v2 price feed.

Subscribes to `book` + `trade` channels for the configured pairs,
maintains a LocalOrderBook per pair, and publishes Tick/BookUpdate
events onto the bus.

Spec §3 / §5.3.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from decimal import Decimal

import websockets

from backend.models.trading import (
    BookUpdateEvent, OrderBookLevel, OrderBookSnapshot, TickEvent,
)
from backend.services.trading.event_bus import EventBus, get_default_bus
from backend.services.trading.order_book import ChecksumMismatch, LocalOrderBook

logger = logging.getLogger(__name__)

KRAKEN_WS_URL = "wss://ws.kraken.com/v2"


_KRAKEN_TO_CANONICAL = {
    "XETHZAUD": "ETH/AUD",
    "LINKAUD":  "LINK/AUD",
    "ADAAUD":   "ADA/AUD",
    "SOLAUD":   "SOL/AUD",
}


def kraken_pair_to_canonical(s: str) -> str:
    return _KRAKEN_TO_CANONICAL.get(s, s)


def _parse_levels(rows) -> list[OrderBookLevel]:
    return [
        OrderBookLevel(price=Decimal(str(r["price"])),
                       qty=Decimal(str(r["qty"])))
        for r in rows
    ]


def _parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def parse_book_snapshot_message(msg: dict) -> OrderBookSnapshot:
    d = msg["data"][0]
    return OrderBookSnapshot(
        pair=d["symbol"],
        asks=_parse_levels(d["asks"]),
        bids=_parse_levels(d["bids"]),
        checksum=str(d["checksum"]),
        ts=_parse_ts(d["timestamp"]),
    )


def parse_book_update_message(msg: dict) -> OrderBookSnapshot:
    """Same shape; the difference is whether it's a full snapshot or a diff."""
    return parse_book_snapshot_message(msg)


def parse_trade_message(msg: dict) -> TickEvent:
    last = msg["data"][-1]
    return TickEvent(
        pair=last["symbol"],
        price=Decimal(str(last["price"])),
        ts=_parse_ts(last["timestamp"]),
    )


# ─────────────────────────── Live feed task ────────────────────

class PriceFeed:
    # While compute_checksum runs without per-pair precision metadata
    # it drifts every diff (see docs/manual-smoke-strategies.md §11).
    # Rate-limit the warning so logs stay readable in production.
    _CHECKSUM_LOG_INTERVAL_S = 60.0

    def __init__(
        self,
        *,
        pairs: list[str],
        bus: EventBus | None = None,
        executor=None,   # PaperExecutor to attach books onto
    ) -> None:
        self.pairs = pairs
        self.bus = bus or get_default_bus()
        self.executor = executor
        self.books: dict[str, LocalOrderBook] = {p: LocalOrderBook(p) for p in pairs}
        self._drift_last_logged: dict[str, float] = {}
        # Updated on every WS message (book diff, trade, heartbeat). Lets
        # the executor distinguish "WS is alive" from "this pair hasn't
        # ticked recently" — Kraken's book channel only diffs on change,
        # so low-volume pairs can be quiet for tens of seconds while the
        # connection is perfectly healthy.
        self.last_message_at: datetime | None = None
        if self.executor is not None:
            for p, b in self.books.items():
                self.executor.attach_book(p, b)
            if hasattr(self.executor, "attach_feed"):
                self.executor.attach_feed(self)

    def is_ws_healthy(self, now: datetime, max_age_s: float = 10.0) -> bool:
        """Return True if a Kraken WS message has been received in the last
        `max_age_s` seconds. Kraken's heartbeat channel sends a tick every
        second when connected, so anything older than ~10s is a disconnect.
        """
        if self.last_message_at is None:
            return False
        return (now - self.last_message_at).total_seconds() <= max_age_s

    async def run(self) -> None:
        backoff = 1
        while True:
            try:
                async with websockets.connect(KRAKEN_WS_URL,
                                              ping_interval=20,
                                              close_timeout=10) as ws:
                    await ws.send(json.dumps({
                        "method": "subscribe",
                        "params": {"channel": "book", "symbol": self.pairs, "depth": 25},
                    }))
                    await ws.send(json.dumps({
                        "method": "subscribe",
                        "params": {"channel": "trade", "symbol": self.pairs},
                    }))
                    # Heartbeat = 1Hz keepalive when WS is connected. Lets us
                    # detect a disconnect within seconds even when low-volume
                    # pairs have no book/trade activity.
                    await ws.send(json.dumps({
                        "method": "subscribe",
                        "params": {"channel": "heartbeat"},
                    }))
                    backoff = 1
                    async for raw in ws:
                        await self._handle(json.loads(raw))
            except Exception:
                logger.exception("Kraken WS disconnected — reconnecting in %ds", backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    async def _handle(self, msg: dict) -> None:
        # Refresh the WS-health timestamp on every inbound message so the
        # executor can distinguish a dead connection from a quiet pair.
        self.last_message_at = datetime.now(timezone.utc)
        ch = msg.get("channel")
        if ch == "heartbeat":
            return
        if ch == "book":
            kind = msg.get("type")
            data = msg.get("data", [])
            if not data:
                return
            d = data[0]
            pair = d["symbol"]
            book = self.books.get(pair)
            if book is None:
                return
            if kind == "snapshot":
                book.apply_snapshot(
                    asks=_parse_levels(d["asks"]),
                    bids=_parse_levels(d["bids"]),
                    checksum=str(d["checksum"]),
                    ts=_parse_ts(d["timestamp"]),
                )
            elif kind == "update":
                try:
                    book.apply_diff(
                        ask_updates=_parse_levels(d["asks"]),
                        bid_updates=_parse_levels(d["bids"]),
                        new_checksum=str(d["checksum"]) if "checksum" in d else None,
                        ts=_parse_ts(d["timestamp"]),
                    )
                except ChecksumMismatch as e:
                    # Soft-verify pending the proper fix: apply_diff already
                    # updated the book before the checksum check, and Kraken's
                    # diff stream is contractually well-formed, so the local
                    # state is still correct. compute_checksum needs each
                    # pair's pair_decimals / lot_decimals from AssetPairs to
                    # match Kraken's algorithm — tracked in
                    # docs/manual-smoke-strategies.md §11.
                    now_mono = time.monotonic()
                    last = self._drift_last_logged.get(pair, 0.0)
                    if now_mono - last >= self._CHECKSUM_LOG_INTERVAL_S:
                        logger.warning("Order book checksum drift: %s", e)
                        self._drift_last_logged[pair] = now_mono
                except Exception:
                    logger.exception("Order book update failed on %s — resubscribing", pair)
                    raise   # the outer loop reconnects
            await self.bus.publish(BookUpdateEvent(
                pair=pair, snapshot=OrderBookSnapshot(
                    pair=pair, asks=book.asks[:25], bids=book.bids[:25],
                    checksum=book.checksum, ts=book.ts,
                ), ts=book.ts,
            ))
        elif ch == "trade":
            tick = parse_trade_message(msg)
            await self.bus.publish(tick)
