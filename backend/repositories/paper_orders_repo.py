"""Repository for paper_orders + paper_fills."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable
from uuid import UUID

from backend.db.supabase_client import get_supabase
from backend.models.trading import Fill, OrderRow


def find_by_idempotency_key(
    strategy_id: UUID, key: str, schema: str = "public",
) -> OrderRow | None:
    sb = get_supabase()
    r = (sb.schema(schema).table("paper_orders")
           .select("*")
           .eq("strategy_id", str(strategy_id))
           .eq("idempotency_key", key)
           .limit(1).execute())
    if not r.data:
        return None
    return OrderRow.model_validate(r.data[0])


def insert_order(
    *,
    strategy_id: UUID, idempotency_key: str, pair: str,
    side: str, type_: str, qty: Decimal, limit_price: Decimal | None,
    expires_at: datetime | None, status: str,
    reject_reason: str | None, decided_by: UUID | None,
    schema: str = "public",
) -> str:
    sb = get_supabase()
    payload = {
        "strategy_id": str(strategy_id),
        "idempotency_key": idempotency_key,
        "pair": pair, "side": side, "type": type_,
        "qty": str(qty), "limit_price": str(limit_price) if limit_price else None,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "status": status, "reject_reason": reject_reason,
        "decided_by": str(decided_by) if decided_by else None,
    }
    r = sb.schema(schema).table("paper_orders").insert(payload).execute()
    return r.data[0]["id"]


def insert_fills(order_id: str, fills: Iterable[Fill], schema: str = "public") -> None:
    sb = get_supabase()
    rows = [{
        "order_id": order_id,
        "qty": str(f.qty), "price": str(f.price),
        "fee_aud": str(f.fee_aud), "fee_role": f.fee_role,
        "book_state_hash": f.book_state_hash,
        "filled_at": f.filled_at.isoformat(),
    } for f in fills]
    if rows:
        sb.schema(schema).table("paper_fills").insert(rows).execute()


def list_open_orders(strategy_id: UUID, schema: str = "public") -> list[OrderRow]:
    sb = get_supabase()
    r = (sb.schema(schema).table("paper_orders").select("*")
           .eq("strategy_id", str(strategy_id))
           .in_("status", ["pending", "partial"])
           .order("created_at").execute())
    return [OrderRow.model_validate(row) for row in (r.data or [])]


def update_order_status(
    order_id: str, status: str,
    reject_reason: str | None = None, schema: str = "public",
) -> None:
    sb = get_supabase()
    (sb.schema(schema).table("paper_orders")
       .update({"status": status, "reject_reason": reject_reason})
       .eq("id", order_id).execute())
