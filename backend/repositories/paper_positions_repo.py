"""Repository for paper_positions. Cash is stored as asset = 'AUD'."""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from backend.db.supabase_client import get_supabase


def get_all(strategy_id: UUID, schema: str = "public") -> dict[str, dict]:
    sb = get_supabase()
    r = (sb.schema(schema).table("paper_positions").select("*")
           .eq("strategy_id", str(strategy_id)).execute())
    return {row["asset"]: row for row in (r.data or [])}


def upsert(
    strategy_id: UUID, asset: str, qty: Decimal,
    avg_cost_aud: Decimal, lots_jsonb: list[dict],
    schema: str = "public",
) -> None:
    sb = get_supabase()
    (sb.schema(schema).table("paper_positions").upsert({
        "strategy_id": str(strategy_id),
        "asset": asset,
        "qty": str(qty),
        "avg_cost_aud": str(avg_cost_aud),
        "lots_jsonb": lots_jsonb,
    }, on_conflict="strategy_id,asset").execute())
