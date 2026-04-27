from fastapi import APIRouter
from backend.models.portfolio import PortfolioSummary
from backend.services import portfolio_service

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/summary", response_model=PortfolioSummary)
async def get_portfolio_summary() -> PortfolioSummary:
    return portfolio_service.build_summary()
