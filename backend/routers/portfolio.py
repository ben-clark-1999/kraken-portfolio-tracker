from fastapi import APIRouter, HTTPException
from backend.models.portfolio import PortfolioSummary
from backend.services import portfolio_service

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary() -> PortfolioSummary:
    try:
        return portfolio_service.build_summary()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
