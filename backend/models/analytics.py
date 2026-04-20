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
