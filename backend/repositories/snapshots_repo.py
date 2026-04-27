"""Data access for the `portfolio_snapshots` table."""

from datetime import datetime, timedelta, timezone

from backend.db.supabase_client import get_supabase
from backend.models.snapshot import PortfolioSnapshot, SnapshotAsset


def _parse_snapshot_row(row: dict) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        id=row["id"],
        captured_at=row["captured_at"],
        total_value_aud=float(row["total_value_aud"]),
        assets={asset: SnapshotAsset(**data) for asset, data in row["assets"].items()},
    )


def get_all(
    from_dt: str | None = None,
    to_dt: str | None = None,
    schema: str = "public",
) -> list[PortfolioSnapshot]:
    db = get_supabase()
    query = (
        db.schema(schema)
        .table("portfolio_snapshots")
        .select("*")
        .order("captured_at", desc=False)
    )
    if from_dt:
        query = query.gte("captured_at", from_dt)
    if to_dt:
        query = query.lte("captured_at", to_dt)
    return [_parse_snapshot_row(row) for row in query.execute().data]


def get_nearest(target_dt: str, schema: str = "public") -> PortfolioSnapshot | None:
    db = get_supabase()
    after = (
        db.schema(schema).table("portfolio_snapshots")
        .select("*").gte("captured_at", target_dt)
        .order("captured_at", desc=False).limit(1).execute()
    )
    before = (
        db.schema(schema).table("portfolio_snapshots")
        .select("*").lt("captured_at", target_dt)
        .order("captured_at", desc=True).limit(1).execute()
    )
    candidates = []
    if after.data:
        candidates.append(after.data[0])
    if before.data:
        candidates.append(before.data[0])
    if not candidates:
        return None
    target = datetime.fromisoformat(target_dt)
    closest = min(
        candidates,
        key=lambda r: abs((datetime.fromisoformat(r["captured_at"]) - target).total_seconds()),
    )
    return _parse_snapshot_row(closest)


def get_oldest(schema: str = "public") -> PortfolioSnapshot | None:
    db = get_supabase()
    result = (
        db.schema(schema).table("portfolio_snapshots")
        .select("*").order("captured_at", desc=False).limit(1).execute()
    )
    if result.data:
        return _parse_snapshot_row(result.data[0])
    return None


def get_existing_dates(schema: str = "public") -> set[str]:
    db = get_supabase()
    result = db.schema(schema).table("portfolio_snapshots").select("captured_at").execute()
    return {row["captured_at"][:10] for row in result.data}


def insert(
    captured_at: str,
    total_value_aud: float,
    assets_json: dict,
    schema: str = "public",
) -> None:
    db = get_supabase()
    db.schema(schema).table("portfolio_snapshots").insert({
        "captured_at": captured_at,
        "total_value_aud": total_value_aud,
        "assets": assets_json,
    }).execute()


def delete_today(schema: str = "public") -> None:
    """Delete all snapshots from today's UTC date.

    Used by save_snapshot to prevent duplicate rows on server restart.
    """
    db = get_supabase()
    today = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    tomorrow = (datetime.now(tz=timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
    db.schema(schema).table("portfolio_snapshots") \
        .delete() \
        .gte("captured_at", f"{today}T00:00:00+00:00") \
        .lt("captured_at", f"{tomorrow}T00:00:00+00:00") \
        .execute()


def clear(schema: str = "public") -> int:
    db = get_supabase()
    result = db.schema(schema).table("portfolio_snapshots") \
        .delete() \
        .gte("captured_at", "1970-01-01T00:00:00+00:00") \
        .execute()
    return len(result.data)
