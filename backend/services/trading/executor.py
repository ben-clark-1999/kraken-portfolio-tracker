"""OrderExecutor Protocol + PaperExecutor implementation.

Spec §5. Same Protocol is later implemented by LiveKrakenExecutor.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from backend.models.trading import OrderResult, OrderRow


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

    def attach_book(self, pair: str, book) -> None:
        self._books[pair] = book

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
        book = self._books.get(pair)
        now = datetime.now(timezone.utc)
        if book is None or book.age_seconds(now) > 5:
            order_id = paper_orders_repo.insert_order(
                strategy_id=strategy_id, idempotency_key=idempotency_key,
                pair=pair, side=side, type_=type, qty=qty,
                limit_price=limit_price, expires_at=expires_at,
                status="rejected", reject_reason="BOOK_UNAVAILABLE",
                decided_by=None, schema=self._schema,
            )
            return OrderResult(order_id=order_id, status="rejected",
                               fills=[], reject_reason="BOOK_UNAVAILABLE")

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
        decision = risk_cap_precheck(state=state, order=intent, caps=caps)
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
                status = "filled" if fills and sum(f.qty for f in fills) == qty else (
                    "partial" if fills else "pending"
                )
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
