from pydantic import BaseModel


class BalanceChange(BaseModel):
    timeframe: str
    start_value_aud: float
    end_value_aud: float
    change_aud: float
    change_pct: float
    start_date: str
    end_date: str
    note: str | None = None


class DCAAnalysisAsset(BaseModel):
    asset: str
    total_invested_aud: float
    average_cost_basis_aud: float
    lot_count: int
    average_days_between_buys: float | None  # None if only 1 lot
    last_buy_date: str
    next_expected_buy_date: str
    cadence_deviation_days: float | None  # None if only 1 lot


class DCAAnalysis(BaseModel):
    assets: list[DCAAnalysisAsset]
    overall: dict  # total_invested_aud, average_cadence_days


class CGTLot(BaseModel):
    lot_id: str
    asset: str
    acquired_at: str
    days_held: int
    quantity: float
    cost_basis_aud: float
    current_value_aud: float
    unrealised_gain_aud: float
    cgt_discount_eligible: bool
    days_until_discount_eligible: int


class CGTSummary(BaseModel):
    total_eligible_gain_aud: float
    total_ineligible_gain_aud: float
    lots_within_30_days_of_eligibility: int


class UnrealisedCGT(BaseModel):
    lots: list[CGTLot]
    summary: CGTSummary


class BuyBreakdown(BaseModel):
    date: str
    aud_spent: float
    actual_asset_bought: str
    actual_qty: float
    hypothetical_qty_of_target: float


class SkippedBuy(BaseModel):
    date: str
    aud_spent: float
    actual_asset_bought: str
    reason: str


class BuyAndHoldComparison(BaseModel):
    asset: str
    total_aud_invested: float
    actual_portfolio_value: float
    hypothetical_value_if_all_in_asset: float
    difference_aud: float
    difference_pct: float
    per_buy_breakdown: list[BuyBreakdown]
    skipped_buys: list[SkippedBuy]


class AssetPerformance(BaseModel):
    start_price_aud: float
    end_price_aud: float
    change_pct: float
    rank: int


class PairRatio(BaseModel):
    start_ratio: float
    end_ratio: float
    change_pct: float


class RelativePerformance(BaseModel):
    timeframe: str
    start_date: str
    end_date: str
    assets: dict[str, AssetPerformance]
    ratios: dict[str, PairRatio]
    best_performer: str
    worst_performer: str
    spread_pct: float
