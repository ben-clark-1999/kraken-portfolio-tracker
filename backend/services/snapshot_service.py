from backend.db.supabase_client import get_supabase
from backend.models.portfolio import PortfolioSummary
from backend.models.snapshot import PortfolioSnapshot, SnapshotAsset


def save_snapshot(summary: PortfolioSummary, schema: str = "public") -> None:
    db = get_supabase()
    assets_json = {
        pos.asset: {
            "quantity": pos.quantity,
            "value_aud": pos.value_aud,
            "price_aud": pos.price_aud,
        }
        for pos in summary.positions
    }
    db.schema(schema).table("portfolio_snapshots").insert({
        "captured_at": summary.captured_at,
        "total_value_aud": summary.total_value_aud,
        "assets": assets_json,
    }).execute()


def get_snapshots(
    from_dt: str | None = None,
    to_dt: str | None = None,
    schema: str = "public",
) -> list[PortfolioSnapshot]:
    db = get_supabase()
    query = db.schema(schema).table("portfolio_snapshots").select("*").order("captured_at", desc=False)
    if from_dt:
        query = query.gte("captured_at", from_dt)
    if to_dt:
        query = query.lte("captured_at", to_dt)
    result = query.execute()
    return [
        PortfolioSnapshot(
            id=row["id"],
            captured_at=row["captured_at"],
            total_value_aud=float(row["total_value_aud"]),
            assets={
                asset: SnapshotAsset(**data)
                for asset, data in row["assets"].items()
            },
        )
        for row in result.data
    ]
