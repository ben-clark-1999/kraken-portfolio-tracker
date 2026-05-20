"""Repository for the `manual_cash_flows` table.

Persists Kraken deposit/withdrawal events that segment the comparison
window for the manual-portfolio leaderboard entry.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from backend.db.supabase_client import get_supabase


def upsert_by_refid(
    *,
    kraken_refid: str,
    kind: str,           # "deposit" | "withdrawal"
    amount_aud: Decimal,
    occurred_at: datetime,
    schema: str = "public",
) -> None:
    """Insert a new cash-flow row, no-op if the refid already exists."""
    sb = get_supabase()
    (sb.schema(schema).table("manual_cash_flows")
       .upsert(
           {
               "kraken_refid": kraken_refid,
               "kind": kind,
               "amount_aud": str(amount_aud),
               "occurred_at": occurred_at.isoformat(),
           },
           on_conflict="kraken_refid",
           ignore_duplicates=True,
       ).execute())


def list_since(*, since: datetime, schema: str = "public") -> list[dict]:
    """Cash-flow rows with occurred_at > since, ascending."""
    sb = get_supabase()
    r = (sb.schema(schema).table("manual_cash_flows")
           .select("*")
           .gt("occurred_at", since.isoformat())
           .order("occurred_at", desc=False).execute())
    return r.data or []


def last_created_at(*, schema: str = "public") -> datetime | None:
    """Max created_at across all rows. Used for debounce."""
    sb = get_supabase()
    r = (sb.schema(schema).table("manual_cash_flows")
           .select("created_at")
           .order("created_at", desc=True).limit(1).execute())
    if not r.data:
        return None
    return datetime.fromisoformat(r.data[0]["created_at"].replace("Z", "+00:00"))


def latest_occurred_at(*, schema: str = "public") -> datetime | None:
    """Max occurred_at across all rows. Used as the 'since' for next scan."""
    sb = get_supabase()
    r = (sb.schema(schema).table("manual_cash_flows")
           .select("occurred_at")
           .order("occurred_at", desc=True).limit(1).execute())
    if not r.data:
        return None
    return datetime.fromisoformat(r.data[0]["occurred_at"].replace("Z", "+00:00"))
