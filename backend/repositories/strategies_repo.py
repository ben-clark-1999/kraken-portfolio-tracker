"""Repository for the `strategies` table."""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from backend.db.supabase_client import get_supabase
from backend.models.trading import StrategyRow


def get(strategy_id: UUID, schema: str = "public") -> StrategyRow | None:
    sb = get_supabase()
    r = (sb.schema(schema).table("strategies")
           .select("*").eq("id", str(strategy_id)).limit(1).execute())
    if not r.data:
        return None
    return StrategyRow.model_validate(r.data[0])


def list_active(schema: str = "public") -> list[StrategyRow]:
    sb = get_supabase()
    r = sb.schema(schema).table("strategies").select("*").eq("status", "active").execute()
    return [StrategyRow.model_validate(row) for row in (r.data or [])]


def update_status(strategy_id: UUID, status: str, schema: str = "public") -> None:
    sb = get_supabase()
    (sb.schema(schema).table("strategies")
       .update({"status": status})
       .eq("id", str(strategy_id)).execute())


def update_persona_stable_since(strategy_id: UUID, ts, schema: str = "public") -> None:
    sb = get_supabase()
    (sb.schema(schema).table("strategies")
       .update({"persona_prompt_stable_since": ts.isoformat()})
       .eq("id", str(strategy_id)).execute())
