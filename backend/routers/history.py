from fastapi import APIRouter, HTTPException, Query
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
    try:
        return snapshot_service.get_snapshots(from_dt=from_dt, to_dt=to_dt)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/trades", response_model=list[DCAEntry])
async def get_dca_history() -> list[DCAEntry]:
    try:
        lots = get_all_lots()
        balances = kraken_service.get_balances()
        prices = kraken_service.get_ticker_prices(list(balances.keys()))
        return portfolio_service.get_dca_history(lots, prices)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
