"""Repository for the `strategies` table."""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from backend.db.supabase_client import get_supabase
from backend.models.trading import StrategyRow


def get(strategy_id: UUID) -> StrategyRow | None:
    sb = get_supabase()
    r = sb.table("strategies").select("*").eq("id", str(strategy_id)).limit(1).execute()
    if not r.data:
        return None
    return StrategyRow.model_validate(r.data[0])


def list_active() -> list[StrategyRow]:
    sb = get_supabase()
    r = sb.table("strategies").select("*").eq("status", "active").execute()
    return [StrategyRow.model_validate(row) for row in (r.data or [])]


def update_status(strategy_id: UUID, status: str) -> None:
    sb = get_supabase()
    sb.table("strategies").update({"status": status,
                                   "updated_at": "now()"}
                                  ).eq("id", str(strategy_id)).execute()


def update_persona_stable_since(strategy_id: UUID, ts) -> None:
    sb = get_supabase()
    sb.table("strategies").update(
        {"persona_prompt_stable_since": ts.isoformat(),
         "updated_at": "now()"}
    ).eq("id", str(strategy_id)).execute()
