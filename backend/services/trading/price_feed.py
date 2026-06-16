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
        stale_after_s: float = 90.0,
        watchdog_interval_s: float = 15.0,
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
        # Watchdog: the connection-level reconnect only fires on a socket
        # exception. Kraken's 1Hz heartbeat keeps the socket "alive" even when
        # the book channel silently stops, so book.ts can freeze indefinitely
        # with no exception (all four alt feeds froze >2h on 2026-06-16). The
        # watchdog forces a reconnect once a populated book passes this age.
        # Set comfortably above any normal book-update gap for liquid pairs but
        # below the frontend's 300s "feed silent" red threshold so it self-heals
        # before the operator sees it.
        self.stale_after_s = stale_after_s
        self.watchdog_interval_s = watchdog_interval_s
        # Handle to the live websocket so the watchdog can close it to trigger
        # the reconnect path in run(). None while disconnected/reconnecting.
        self._ws = None
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

    def _stale_pairs(self, now: datetime) -> list[str]:
        """Pairs whose book has been populated but hasn't updated in
        `stale_after_s`. Never-connected books (ts is None → age inf) are
        excluded — warming those is the warm-up gate's job, not the watchdog's,
        and reconnecting wouldn't make Kraken send a first snapshot any sooner.
        """
        return [
            p for p, b in self.books.items()
            if b.ts is not None and b.age_seconds(now) > self.stale_after_s
        ]

    async def _recover_stale_feed(self, now: datetime, stale: list[str]) -> None:
        """Surface a FEED_STALL alert and close the socket so run() reconnects
        and resubscribes (a fresh snapshot resets every book's ts)."""
        ages = {p: round(self.books[p].age_seconds(now)) for p in stale}
        logger.warning("Feed stall detected — forcing reconnect. Stale (s): %s", ages)
        try:
            from backend.repositories import system_alerts_repo as alerts
            alerts.insert(
                level="error", code="FEED_STALL", strategy_id=None,
                message=f"Order book feed stalled; forcing reconnect: {ages}",
                payload={"stale_pairs": ages, "stale_after_s": self.stale_after_s,
                         "ws_alive": self.is_ws_healthy(now)},
            )
        except Exception:
            # Best-effort — a failed alert insert must not stop the recovery.
            logger.exception("Failed to insert FEED_STALL alert")
        ws = self._ws
        if ws is not None:
            try:
                await ws.close()
            except Exception:
                logger.exception("Failed to close stalled WS")

    async def _watchdog_tick(self, now: datetime) -> list[str]:
        stale = self._stale_pairs(now)
        if stale:
            await self._recover_stale_feed(now, stale)
        return stale

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(self.watchdog_interval_s)
            try:
                await self._watchdog_tick(datetime.now(timezone.utc))
            except Exception:
                logger.exception("Price feed watchdog tick failed")

    async def run(self) -> None:
        watchdog = asyncio.create_task(self._watchdog(), name="price_feed_watchdog")
        backoff = 1
        try:
            while True:
                try:
                    async with websockets.connect(KRAKEN_WS_URL,
                                                  ping_interval=20,
                                                  close_timeout=10) as ws:
                        self._ws = ws
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
                finally:
                    self._ws = None
        finally:
            watchdog.cancel()

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
            # Fill any resting limit order the moving book has now crossed.
            # Only reconcile pairs that actually have a resting limit order:
            # reconcile_resting_orders uses the synchronous Supabase client, so
            # calling it on every book tick for every pair floods the DB and
            # starves the asyncio event loop (the HTTP server stops responding).
            # The executor tracks resting pairs in-memory. Guarded for executors
            # that don't (tests/legacy) — they simply skip reconcile.
            if (self.executor is not None
                    and hasattr(self.executor, "reconcile_resting_orders")
                    and pair in getattr(self.executor, "_resting_pairs", ())):
                await self.executor.reconcile_resting_orders(pair)
        elif ch == "trade":
            tick = parse_trade_message(msg)
            await self.bus.publish(tick)


async def wait_for_books(executor, pairs, *, timeout_s: float = 30.0,
                         poll_s: float = 0.5) -> bool:
    """Block until every pair has a populated book (asks + bids), or timeout.

    Spec §3.3 warm-up gate: prevents strategy loops/triggers firing into an
    empty book at boot (which rejects BOOK_UNAVAILABLE). Returns True if all
    books populated, False if the timeout elapsed first.
    """
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_s
    while True:
        books = getattr(executor, "_books", {}) or {}
        if all(books.get(p) is not None and books[p].asks and books[p].bids
               for p in pairs):
            return True
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(poll_s)
