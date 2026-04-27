"""Data access for the `lots` table.

All Supabase concerns live here. Service layer stays free of `db.table().*`
chains.
"""

from backend.db.supabase_client import get_supabase
from backend.models.trade import Lot


def get_all(schema: str = "public") -> list[Lot]:
    """Return all lots, oldest first."""
    db = get_supabase()
    result = (
        db.schema(schema)
        .table("lots")
        .select("*")
        .order("acquired_at", desc=False)
        .execute()
    )
    return [Lot(**row) for row in result.data]


def get_existing_trade_ids(trade_ids: list[str], schema: str = "public") -> set[str]:
    """Given a list of candidate trade IDs, return the subset that already exist."""
    if not trade_ids:
        return set()
    db = get_supabase()
    result = (
        db.schema(schema)
        .table("lots")
        .select("kraken_trade_id")
        .in_("kraken_trade_id", trade_ids)
        .execute()
    )
    return {row["kraken_trade_id"] for row in result.data}


def insert(rows: list[dict], schema: str = "public") -> None:
    """Insert lot rows. Caller is responsible for filtering duplicates."""
    if not rows:
        return
    db = get_supabase()
    db.schema(schema).table("lots").insert(rows).execute()
