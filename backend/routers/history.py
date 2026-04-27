from fastapi import APIRouter, Query
from backend.models.snapshot import PortfolioSnapshot
from backend.models.trade import DCAEntry
from backend.services import snapshot_service, portfolio_service, kraken_service
from backend.services.sync_service import get_all_lots

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("/snapshots", response_model=list[PortfolioSnapshot])
async def get_snapshots(
    from_dt: str | None = Query(default=None),
    to_dt: str | None = Query(default=None),
) -> list[PortfolioSnapshot]:
    return snapshot_service.get_snapshots(from_dt=from_dt, to_dt=to_dt)


@router.get("/trades", response_model=list[DCAEntry])
async def get_dca_history() -> list[DCAEntry]:
    lots = get_all_lots()
    balances = kraken_service.get_balances()
    prices = kraken_service.get_ticker_prices(list(balances.keys()))
    return portfolio_service.get_dca_history(lots, prices)


@router.post("/backfill")
async def backfill_snapshots(clear: bool = Query(default=False)) -> dict:
    """Reconstruct daily snapshots from Kraken ledger + OHLC data.

    Pass ?clear=true to wipe existing snapshots first (useful after adding
    new assets so their history is included from the start).
    """
    cleared = 0
    if clear:
        cleared = snapshot_service.clear_snapshots()
    count = snapshot_service.backfill_from_ledger()
    return {"cleared": cleared, "backfilled": count}
