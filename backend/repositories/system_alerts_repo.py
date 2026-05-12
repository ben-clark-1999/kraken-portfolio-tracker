"""Repository for system_alerts."""
from __future__ import annotations

from uuid import UUID

from backend.db.supabase_client import get_supabase


def insert(*, level: str, code: str, strategy_id: UUID | None,
           message: str, payload: dict | None = None,
           schema: str = "public") -> str:
    sb = get_supabase()
    r = sb.schema(schema).table("system_alerts").insert({
        "level": level, "code": code,
        "strategy_id": str(strategy_id) if strategy_id else None,
        "message": message, "payload": payload or {},
    }).execute()
    return r.data[0]["id"]


def list_unacknowledged(limit: int = 50, schema: str = "public") -> list[dict]:
    sb = get_supabase()
    r = (sb.schema(schema).table("system_alerts").select("*")
           .is_("acknowledged_at", "null")
           .order("created_at", desc=True).limit(limit).execute())
    return r.data or []
