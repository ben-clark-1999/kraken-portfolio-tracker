from pydantic import BaseModel


class Lot(BaseModel):
    id: str
    asset: str
    acquired_at: str   # ISO datetime string, AEST
    quantity: float
    cost_aud: float
    cost_per_unit_aud: float
    kraken_trade_id: str
    remaining_quantity: float


class DCAEntry(BaseModel):
    lot_id: str
    asset: str
    acquired_at: str
    quantity: float
    cost_aud: float
    cost_per_unit_aud: float
    current_price_aud: float
    current_value_aud: float
    unrealised_pnl_aud: float
