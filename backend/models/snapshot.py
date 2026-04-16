from pydantic import BaseModel


class SnapshotAsset(BaseModel):
    quantity: float
    value_aud: float
    price_aud: float


class PortfolioSnapshot(BaseModel):
    id: str
    captured_at: str
    total_value_aud: float
    assets: dict[str, SnapshotAsset]
