"""Data access for the `sync_log` table."""

from backend.db.supabase_client import get_supabase


def get_last_synced_trade_id(schema: str = "public") -> str | None:
    """Return the most recent successful sync's trade_id, or None."""
    db = get_supabase()
    result = (
        db.schema(schema).table("sync_log")
        .select("last_trade_id")
        .eq("status", "success")
        .order("synced_at", desc=True)
        .limit(1)
        .execute()
    )
    rows = result.data
    if rows and rows[0]["last_trade_id"]:
        return rows[0]["last_trade_id"]
    return None


def insert(
    last_trade_id: str | None,
    status: str,
    error_message: str | None = None,
    schema: str = "public",
) -> None:
    """Insert a sync_log row."""
    db = get_supabase()
    db.schema(schema).table("sync_log").insert({
        "last_trade_id": last_trade_id,
        "status": status,
        "error_message": error_message,
    }).execute()
