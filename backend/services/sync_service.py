from decimal import Decimal
from backend.db.supabase_client import get_supabase
from backend.models.trade import Lot
from backend.repositories import lots_repo
from backend.utils.timezone import unix_to_aest, to_iso


def get_last_synced_trade_id() -> str | None:
    """Returns the most recently synced trade_id from sync_log, or None."""
    db = get_supabase()
    result = (
        db.table("sync_log")
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


def upsert_lots(trades: list[dict]) -> str | None:
    """
    Converts raw trade dicts into lot rows and inserts only trades not already
    in the database.

    Returns the trade_id of the first trade in the input (most recent),
    or None if trades is empty.
    """
    if not trades:
        return None

    trade_ids = [t["trade_id"] for t in trades]
    existing_ids = lots_repo.get_existing_trade_ids(trade_ids)

    new_trades = [t for t in trades if t["trade_id"] not in existing_ids]
    if new_trades:
        rows = []
        for trade in new_trades:
            acquired_at = to_iso(unix_to_aest(trade["time"]))
            quantity = Decimal(trade["vol"])
            cost_per_unit = Decimal(trade["price"])
            cost_aud = Decimal(trade["cost"])
            rows.append({
                "asset": trade["asset"],
                "acquired_at": acquired_at,
                "quantity": str(quantity),
                "cost_aud": str(cost_aud),
                "cost_per_unit_aud": str(cost_per_unit),
                "kraken_trade_id": trade["trade_id"],
                "remaining_quantity": str(quantity),
            })
        lots_repo.insert(rows)

    return trades[0]["trade_id"]


def record_sync(last_trade_id: str | None, status: str, error_message: str | None = None) -> None:
    """Writes a row to sync_log."""
    db = get_supabase()
    db.table("sync_log").insert({
        "last_trade_id": last_trade_id,
        "status": status,
        "error_message": error_message,
    }).execute()


def get_all_lots() -> list[Lot]:
    """Returns all lots from Supabase ordered oldest first.

    Thin wrapper kept for backward compatibility with existing call sites
    (router and MCP tool). New code should call lots_repo.get_all() directly.
    """
    return lots_repo.get_all()
