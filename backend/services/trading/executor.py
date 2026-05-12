"""OrderExecutor Protocol + PaperExecutor implementation.

Spec §5. Same Protocol is later implemented by LiveKrakenExecutor.
"""
from __future__ import annotations

from datetime import datetime
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
    """

    def __init__(self) -> None:
        # Populated in Task 16 by the price_feed_task.
        self._books: dict = {}

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
        raise NotImplementedError("implemented in Task 11/12")

    async def cancel_order(self, *, order_id: UUID) -> None:
        from backend.repositories import paper_orders_repo
        paper_orders_repo.update_order_status(str(order_id), "cancelled")

    async def get_open_orders(self, *, strategy_id: UUID) -> list[OrderRow]:
        from backend.repositories import paper_orders_repo
        return paper_orders_repo.list_open_orders(strategy_id)
