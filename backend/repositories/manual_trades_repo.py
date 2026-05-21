"""Repository for the `manual_trades` table.

Persists Kraken spot trades (spend+receive ledger pairs) so the manual
leaderboard row never needs a live Kraken call at request time. Populated
by manual_cash_flow_scanner from the same ledger fetch that maintains
manual_cash_flows.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from backend.db.supabase_client import get_supabase


def upsert_by_refid(
    *,
    kraken_refid: str,
    side: str,                 # "buy" | "sell"
    base_asset: str,
    base_qty: Decimal,
    aud_amount: Decimal,
    fee_aud: Decimal,
    occurred_at: datetime,
    schema: str = "public",
) -> None:
    sb = get_supabase()
    (sb.schema(schema).table("manual_trades")
       .upsert(
           {
               "kraken_refid": kraken_refid,
               "side": side,
               "base_asset": base_asset,
               "base_qty": str(base_qty),
               "aud_amount": str(aud_amount),
               "fee_aud": str(fee_aud),
               "occurred_at": occurred_at.isoformat(),
           },
           on_conflict="kraken_refid",
           ignore_duplicates=True,
       ).execute())


def list_since(*, since: datetime, schema: str = "public") -> list[dict]:
    sb = get_supabase()
    r = (sb.schema(schema).table("manual_trades")
           .select("*")
           .gte("occurred_at", since.isoformat())
           .order("occurred_at", desc=False).execute())
    return r.data or []
