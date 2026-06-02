"""OrderExecutor Protocol + PaperExecutor implementation.

Spec §5. Same Protocol is later implemented by LiveKrakenExecutor.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from backend.models.trading import OrderResult, OrderRow

logger = logging.getLogger(__name__)


class OrderExecutor(Protocol):
    async def submit_order(
        self,
        *,
        strategy_id: UUID,
        idempotency_key: str,
        pair: str,
        side: Literal["buy", "sell"],
        type: Literal["market", "limit"],
        qty: Decimal,
        limit_price: Decimal | None = None,
        expires_at: datetime | None = None,
    ) -> OrderResult: ...

    async def cancel_order(self, *, order_id: UUID) -> None: ...

    async def get_open_orders(self, *, strategy_id: UUID) -> list[OrderRow]: ...


class PaperExecutor:
    """In-process simulator. Walks the local L2 book for realistic fills.

    The two heavy methods (submit_order_market_path and the limit reconciler)
    are added in Tasks 11 and 12.

    `schema` selects which Postgres schema the repos hit. Production uses
    "public"; integration tests pass "test".
    """

    def __init__(self, schema: str = "public") -> None:
        # Populated in Task 16 by the price_feed_task.
        self._books: dict = {}
        self._schema = schema
        # PriceFeed sets this so the executor can use connection-level
        # health (heartbeat channel) rather than per-pair book.ts age,
        # which goes "stale" any time a pair has no recent trading.
        self._feed = None
        # Pairs with a resting (pending/partial) limit order. The price feed
        # only reconciles these on book updates — reconciling every pair on
        # every tick floods the DB (sync client) and starves the event loop.
        self._resting_pairs: set[str] = set()
        # Cache of each pair's Kraken minimums {pair: {"ordermin", "costmin"}}.
        # Fetched lazily on first order for a pair (they don't change often).
        self._pair_minimums: dict[str, dict[str, Decimal]] = {}

    def _min_order_aud(self, pair: str, ref_price: Decimal) -> Decimal | None:
        """The AUD floor for `pair` (enforces Kraken ordermin AND costmin).

        Returns None if Kraken minimums can't be fetched — fail-open so a
        transient Kraken outage doesn't block all trading; the absence is
        logged so it's visible.
        """
        from backend.services.trading.min_order import (
            fetch_asset_pairs, min_notional_aud,
        )
        if pair not in self._pair_minimums:
            try:
                self._pair_minimums[pair] = fetch_asset_pairs([pair])[pair]
            except Exception as e:  # noqa: BLE001 — fail-open, just log
                logger.warning("min-order: no Kraken minimums for %s (%s)", pair, e)
                return None
        mins = self._pair_minimums[pair]
        return min_notional_aud(
            ordermin=mins["ordermin"], costmin=mins["costmin"], price=ref_price,
        )

    def prime_resting_pairs(self) -> None:
        """Populate `_resting_pairs` from pending/partial limit orders already
        in the DB (e.g. after a restart) so the feed reconciles them again."""
        from backend.db.supabase_client import get_supabase
        sb = get_supabase()
        rows = (sb.schema(self._schema).table("paper_orders").select("pair")
                  .in_("status", ["pending", "partial"]).eq("type", "limit")
                  .execute().data or [])
        self._resting_pairs = {r["pair"] for r in rows}

    def attach_book(self, pair: str, book) -> None:
        self._books[pair] = book

    def attach_feed(self, feed) -> None:
        self._feed = feed

    def _book_unavailable_reason(self, pair: str, now: datetime) -> str | None:
        """Return a short reason if the book/feed isn't usable, else None.

        Distinguishes three failure modes:
        - book missing or never populated
        - WS connection is dead (no message in 10s; heartbeat ticks 1Hz when alive)
        - no PriceFeed attached AND book.ts is hours old (test/legacy fallback)

        Returning None means: book has levels AND a healthy connection is
        producing updates; safe to execute.
        """
        book = self._books.get(pair)
        if book is None or not book.asks or not book.bids:
            return "no_book"
        if self._feed is not None:
            if not self._feed.is_ws_healthy(now, max_age_s=10.0):
                return "ws_stale"
        elif book.age_seconds(now) > 300:
            # No feed attached (tests). Fall back to a generous book.ts
            # threshold so genuinely-stale fake books still reject.
            return "book_too_old"
        return None

    async def submit_order(
        self,
        *,
        strategy_id: UUID,
        idempotency_key: str,
        pair: str,
        side: Literal["buy", "sell"],
        type: Literal["market", "limit"],
        qty: Decimal,
        limit_price: Decimal | None = None,
        expires_at: datetime | None = None,
    ) -> OrderResult:
        from backend.repositories import (
            paper_orders_repo, paper_positions_repo, strategies_repo,
        )
        from backend.services.trading.fill_model import (
            walk_book_for_market, walk_book_for_limit, InsufficientDepth,
        )
        from backend.services.trading.risk_caps import (
            OrderIntent, PortfolioState, risk_cap_precheck,
        )

        # 1. Idempotency.
        existing = paper_orders_repo.find_by_idempotency_key(
            strategy_id, idempotency_key, schema=self._schema,
        )
        if existing is not None:
            return OrderResult(
                order_id=str(existing.id), status=existing.status,
                fills=[], reject_reason=existing.reject_reason,
            )

        strategy = strategies_repo.get(strategy_id, schema=self._schema)
        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} not found")
        caps = strategy.risk_caps

        # 2. Book availability.
        now = datetime.now(timezone.utc)
        if self._book_unavailable_reason(pair, now) is not None:
            order_id = paper_orders_repo.insert_order(
                strategy_id=strategy_id, idempotency_key=idempotency_key,
                pair=pair, side=side, type_=type, qty=qty,
                limit_price=limit_price, expires_at=expires_at,
                status="rejected", reject_reason="BOOK_UNAVAILABLE",
                decided_by=None, schema=self._schema,
            )
            return OrderResult(order_id=order_id, status="rejected",
                               fills=[], reject_reason="BOOK_UNAVAILABLE")
        book = self._books[pair]

        # 3. Risk-cap pre-check.
        portfolio_rows = paper_positions_repo.get_all(strategy_id, schema=self._schema)
        cash = Decimal(portfolio_rows.get("AUD", {}).get("qty", "0"))
        base_asset = pair.split("/")[0]
        positions = {}
        for a, r in portfolio_rows.items():
            if a == "AUD":
                continue
            # Approximate per-asset AUD value with the current pair's mid for the
            # base asset, and avg_cost for others. Good enough for the pre-check.
            if a == base_asset:
                positions[a] = Decimal(r["qty"]) * book.mid()
            else:
                positions[a] = Decimal(r["qty"]) * Decimal(r.get("avg_cost_aud", "0") or "0")

        ref_price = book.mid() if type == "market" else (limit_price or book.mid())
        notional = qty * ref_price
        intent = OrderIntent(pair=pair, side=side, notional_aud=notional)
        state = PortfolioState(
            cash_aud=cash, positions=positions,
            session_loss_aud=Decimal("0"),   # filled in by Task 25
            drawdown_pct=Decimal("0"),
        )
        decision = risk_cap_precheck(
            state=state, order=intent, caps=caps,
            min_order_aud=self._min_order_aud(pair, ref_price),
        )
        if not decision.accepted:
            order_id = paper_orders_repo.insert_order(
                strategy_id=strategy_id, idempotency_key=idempotency_key,
                pair=pair, side=side, type_=type, qty=qty,
                limit_price=limit_price, expires_at=expires_at,
                status="rejected", reject_reason=decision.reject_reason,
                decided_by=None, schema=self._schema,
            )
            return OrderResult(order_id=order_id, status="rejected",
                               fills=[], reject_reason=decision.reject_reason)

        # 4. Fill.
        try:
            if type == "market":
                fills = walk_book_for_market(book=book, side=side, qty=qty)
                status = "filled"
            else:
                fills = walk_book_for_limit(book=book, side=side, qty=qty,
                                            limit_price=limit_price)
                if not fills:
                    if expires_at is None:
                        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
                    status = "pending"
                elif sum(f.qty for f in fills) == qty:
                    status = "filled"
                else:
                    if expires_at is None:
                        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
                    status = "partial"
        except InsufficientDepth:
            order_id = paper_orders_repo.insert_order(
                strategy_id=strategy_id, idempotency_key=idempotency_key,
                pair=pair, side=side, type_=type, qty=qty,
                limit_price=limit_price, expires_at=expires_at,
                status="rejected", reject_reason="INSUFFICIENT_DEPTH",
                decided_by=None, schema=self._schema,
            )
            return OrderResult(order_id=order_id, status="rejected",
                               fills=[], reject_reason="INSUFFICIENT_DEPTH")

        # 5. Persist.
        order_id = paper_orders_repo.insert_order(
            strategy_id=strategy_id, idempotency_key=idempotency_key,
            pair=pair, side=side, type_=type, qty=qty,
            limit_price=limit_price, expires_at=expires_at,
            status=status, reject_reason=None, decided_by=None,
            schema=self._schema,
        )
        paper_orders_repo.insert_fills(order_id, fills, schema=self._schema)

        # Track resting limit orders so the feed reconciles only this pair.
        if type == "limit" and status in ("pending", "partial"):
            self._resting_pairs.add(pair)

        # 6. Update positions (cash + asset).
        await self._apply_positions(strategy_id, pair, side, fills)

        return OrderResult(order_id=order_id, status=status, fills=fills)

    async def _apply_positions(self, strategy_id, pair, side, fills):
        from backend.repositories import paper_positions_repo
        if not fills:
            return
        asset = pair.split("/")[0]
        rows = paper_positions_repo.get_all(strategy_id, schema=self._schema)
        cash = Decimal(rows.get("AUD", {}).get("qty", "0"))
        asset_qty = Decimal(rows.get(asset, {}).get("qty", "0"))
        asset_cost = Decimal(rows.get(asset, {}).get("avg_cost_aud", "0"))
        lots = rows.get(asset, {}).get("lots_jsonb", []) or []
        for f in fills:
            notional = f.qty * f.price
            fee = f.fee_aud
            if side == "buy":
                cash -= (notional + fee)
                new_qty = asset_qty + f.qty
                new_cost = (
                    ((asset_qty * asset_cost) + (f.qty * f.price)) / new_qty
                    if new_qty > 0 else Decimal("0")
                )
                lots.append({"qty": str(f.qty), "cost_aud": str(f.price),
                             "acquired_at": f.filled_at.isoformat()})
                asset_qty = new_qty
                asset_cost = new_cost
            else:
                cash += (notional - fee)
                # FIFO pop
                remaining = f.qty
                while remaining > 0 and lots:
                    lot = lots[0]
                    lot_qty = Decimal(lot["qty"])
                    take = min(lot_qty, remaining)
                    lot_qty -= take
                    remaining -= take
                    if lot_qty == 0:
                        lots.pop(0)
                    else:
                        lot["qty"] = str(lot_qty)
                asset_qty -= f.qty
        paper_positions_repo.upsert(
            strategy_id, "AUD", cash, Decimal("1"), [], schema=self._schema,
        )
        paper_positions_repo.upsert(
            strategy_id, asset, asset_qty, asset_cost, lots, schema=self._schema,
        )

    async def cancel_order(self, *, order_id: UUID) -> None:
        from backend.repositories import paper_orders_repo
        paper_orders_repo.update_order_status(
            str(order_id), "cancelled", schema=self._schema,
        )

    async def get_open_orders(self, *, strategy_id: UUID) -> list[OrderRow]:
        from backend.repositories import paper_orders_repo
        return paper_orders_repo.list_open_orders(strategy_id, schema=self._schema)

    async def reconcile_resting_orders(self, pair: str) -> None:
        """Walk pending/partial limit orders on `pair`; fill those the book has
        crossed (maker fee). Expired orders are marked 'expired'.
        """
        from backend.db.supabase_client import get_supabase
        from backend.repositories import paper_orders_repo
        from backend.services.trading.fees import KRAKEN_PRO_SPOT_TIER_1, apply_fee
        from backend.models.trading import Fill

        now = datetime.now(timezone.utc)
        # Skip when the book or feed is unhealthy — during a WS disconnect
        # the local book still has levels from the last update, but those
        # prices may no longer reflect the real Kraken book. The next
        # reconcile tick after the feed recovers picks the orders up.
        if self._book_unavailable_reason(pair, now) is not None:
            return
        book = self._books[pair]
        sb = get_supabase()
        rows = (sb.schema(self._schema).table("paper_orders").select("*")
                  .eq("pair", pair)
                  .in_("status", ["pending", "partial"])
                  .eq("type", "limit")
                  .execute().data or [])
        if not rows:
            # Nothing resting on this pair anymore — stop reconciling it.
            self._resting_pairs.discard(pair)
            return
        for r in rows:
            limit_price = Decimal(r["limit_price"])
            side = r["side"]
            order_id = r["id"]
            # Expiry first.
            if r.get("expires_at"):
                exp = datetime.fromisoformat(r["expires_at"].replace("Z", "+00:00"))
                if exp <= now:
                    paper_orders_repo.update_order_status(
                        order_id, "expired", schema=self._schema,
                    )
                    continue
            # Determine remaining qty.
            filled_so_far = (sb.schema(self._schema).table("paper_fills")
                               .select("qty").eq("order_id", order_id)
                               .execute().data or [])
            already = sum(Decimal(f["qty"]) for f in filled_so_far)
            remaining = Decimal(r["qty"]) - already
            if remaining <= 0:
                paper_orders_repo.update_order_status(
                    order_id, "filled", schema=self._schema,
                )
                continue
            # Does the book cross?
            if side == "buy":
                if not book.asks or book.asks[0].price > limit_price:
                    continue
                levels = book.asks
                cap_dir = "max"
            else:
                if not book.bids or book.bids[0].price < limit_price:
                    continue
                levels = book.bids
                cap_dir = "min"
            # Walk levels; charge MAKER (we'd been resting).
            taken_fills: list[Fill] = []
            rem = remaining
            for lvl in levels:
                if cap_dir == "max" and lvl.price > limit_price:
                    break
                if cap_dir == "min" and lvl.price < limit_price:
                    break
                take = min(lvl.qty, rem)
                if take <= 0:
                    continue
                fee = apply_fee(qty=take, price=lvl.price, role="maker",
                                schedule=KRAKEN_PRO_SPOT_TIER_1)
                taken_fills.append(Fill(
                    qty=take, price=lvl.price, fee_aud=fee, fee_role="maker",
                    book_state_hash=book.checksum, filled_at=now,
                ))
                rem -= take
                if rem == 0:
                    break
            if not taken_fills:
                continue
            paper_orders_repo.insert_fills(order_id, taken_fills, schema=self._schema)
            new_status = "filled" if rem == 0 else "partial"
            paper_orders_repo.update_order_status(order_id, new_status, schema=self._schema)
            await self._apply_positions(UUID(r["strategy_id"]), pair, side, taken_fills)
