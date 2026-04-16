from fastapi import APIRouter, HTTPException
from backend.models.portfolio import PortfolioSummary
from backend.services import kraken_service, portfolio_service, snapshot_service
from backend.services.sync_service import get_all_lots

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary() -> PortfolioSummary:
    try:
        balances = kraken_service.get_balances()
        prices = kraken_service.get_ticker_prices(list(balances.keys()))
        lots = get_all_lots()
        summary = portfolio_service.calculate_summary(balances, prices, lots)

        if snapshot_service.should_snapshot():
            snapshot_service.save_snapshot(summary)

        return summary
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
