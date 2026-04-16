from pydantic import BaseModel


class AssetPosition(BaseModel):
    asset: str
    quantity: float
    price_aud: float
    value_aud: float
    cost_basis_aud: float
    unrealised_pnl_aud: float
    allocation_pct: float


class PortfolioSummary(BaseModel):
    total_value_aud: float
    positions: list[AssetPosition]
    captured_at: str   # ISO datetime string, AEST
    next_dca_date: str | None  # ISO date string
