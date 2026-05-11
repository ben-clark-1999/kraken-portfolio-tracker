"""Data access for `up_sync_log` (sync state bookmark)."""

from datetime import datetime

from backend.db.supabase_client import get_supabase


def record_start(schema: str = "public") -> str:
    db = get_supabase()
    result = db.schema(schema).table("up_sync_log").insert({
        "status": "in_progress",
    }).execute()
    return result.data[0]["id"]


def finalize_success(sync_id: str, *, last_seen_tx_at: datetime | None, schema: str = "public") -> None:
    db = get_supabase()
    db.schema(schema).table("up_sync_log").update({
        "status": "success",
        "last_seen_tx_at": last_seen_tx_at.isoformat() if last_seen_tx_at else None,
    }).eq("id", sync_id).execute()


def finalize_error(sync_id: str, *, error_message: str, schema: str = "public") -> None:
    db = get_supabase()
    db.schema(schema).table("up_sync_log").update({
        "status": "error",
        "error_message": error_message,
    }).eq("id", sync_id).execute()


def latest(schema: str = "public") -> dict | None:
    db = get_supabase()
    result = (
        db.schema(schema).table("up_sync_log").select("*")
        .order("synced_at", desc=True).limit(1).execute()
    )
    return result.data[0] if result.data else None


def last_successful_seen_tx_at(schema: str = "public") -> datetime | None:
    db = get_supabase()
    result = (
        db.schema(schema).table("up_sync_log").select("last_seen_tx_at")
        .eq("status", "success")
        .order("synced_at", desc=True).limit(1).execute()
    )
    if not result.data:
        return None
    val = result.data[0]["last_seen_tx_at"]
    return datetime.fromisoformat(val) if val else None
