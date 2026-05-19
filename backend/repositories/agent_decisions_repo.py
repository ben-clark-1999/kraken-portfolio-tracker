"""Repository for agent_decisions."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from backend.db.supabase_client import get_supabase


def insert(
    *,
    strategy_id: UUID, execution_mode: str,
    trigger_event: dict, input_snapshot: dict,
    persona_prompt_hash: str | None,
    model: str | None, input_tokens: int, output_tokens: int,
    cost_aud: Decimal, tool_calls: list, agent_output: str | None,
    latency_ms: int | None, error: str | None,
    schema: str = "public",
) -> str:
    sb = get_supabase()
    r = sb.schema(schema).table("agent_decisions").insert({
        "strategy_id": str(strategy_id),
        "execution_mode": execution_mode,
        "trigger_event": trigger_event,
        "input_snapshot": input_snapshot,
        "persona_prompt_hash": persona_prompt_hash,
        "model": model,
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "cost_aud": str(cost_aud),
        "tool_calls": tool_calls, "agent_output": agent_output,
        "latency_ms": latency_ms, "error": error,
    }).execute()
    return r.data[0]["id"]


def list_recent(strategy_id: UUID, n: int = 5, schema: str = "public") -> list[dict]:
    sb = get_supabase()
    r = (sb.schema(schema).table("agent_decisions").select("*")
           .eq("strategy_id", str(strategy_id))
           .order("created_at", desc=True).limit(n).execute())
    return r.data or []


def mark_notified(decision_id: str, schema: str = "public") -> bool:
    """Set notified_at = now() iff currently NULL. Returns True if the
    update changed a row (i.e. this is the first notify), False if the
    decision was already notified.
    """
    from datetime import datetime, timezone
    sb = get_supabase()
    r = (sb.schema(schema).table("agent_decisions")
           .update({"notified_at": datetime.now(timezone.utc).isoformat()})
           .eq("id", decision_id)
           .is_("notified_at", "null")
           .execute())
    return bool(r.data)
