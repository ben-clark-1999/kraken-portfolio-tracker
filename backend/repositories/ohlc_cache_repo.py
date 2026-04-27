"""Data access for the `ohlc_cache` table."""

from backend.db.supabase_client import get_supabase


def get_by_pair(pair: str, schema: str = "public") -> dict[str, float]:
    """Return cached OHLC close prices for a pair as {YYYY-MM-DD: close}."""
    db = get_supabase()
    result = (
        db.schema(schema).table("ohlc_cache")
        .select("date, close_price")
        .eq("pair", pair)
        .execute()
    )
    return {row["date"]: float(row["close_price"]) for row in result.data}


def upsert(rows: list[dict], schema: str = "public") -> None:
    """Upsert OHLC cache rows. Each row: {pair, date, close_price}."""
    if not rows:
        return
    db = get_supabase()
    db.schema(schema).table("ohlc_cache").upsert(rows, on_conflict="pair,date").execute()
