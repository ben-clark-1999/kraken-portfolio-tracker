"""Pydantic models for the Tax Hub feature.

Three parallel entry kinds (deductible, income, tax_paid) share a TaxEntry
shape. The `type` field carries a kind-specific enum, validated at the
service layer.
"""

from enum import Enum

from pydantic import BaseModel, Field


class TaxEntryKind(str, Enum):
    DEDUCTIBLE = "deductible"
    INCOME = "income"
    TAX_PAID = "tax_paid"


class DeductibleType(str, Enum):
    SOFTWARE = "software"
    HARDWARE = "hardware"
    PROFESSIONAL_DEVELOPMENT = "professional_development"
    PROFESSIONAL_SERVICES = "professional_services"
    CRYPTO_RELATED = "crypto_related"
    OTHER = "other"


class IncomeType(str, Enum):
    SALARY_WAGES = "salary_wages"
    FREELANCE = "freelance"
    INTEREST = "interest"
    DIVIDENDS = "dividends"
    OTHER = "other"


class TaxPaidType(str, Enum):
    PAYG_WITHHOLDING = "payg_withholding"
    PAYG_INSTALLMENT = "payg_installment"
    BAS_PAYMENT = "bas_payment"
    OTHER = "other"


class TaxAttachment(BaseModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    uploaded_at: str


class TaxEntry(BaseModel):
    id: str
    description: str
    amount_aud: float
    date: str             # date_paid or date_received, normalized
    type: str             # one of the kind-specific enums (string for cross-kind compat)
    notes: str | None
    financial_year: str
    attachments: list[TaxAttachment]
    created_at: str
    updated_at: str


class TaxEntryCreate(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    amount_aud: float = Field(gt=0)
    date: str            # ISO date YYYY-MM-DD
    type: str            # validated against the right enum in service layer
    notes: str | None = Field(default=None, max_length=4000)
    attachment_ids: list[str] = []


class TaxEntryUpdate(BaseModel):
    description: str | None = Field(default=None, min_length=1, max_length=200)
    amount_aud: float | None = Field(default=None, gt=0)
    date: str | None = None
    type: str | None = None
    notes: str | None = Field(default=None, max_length=4000)


class KrakenAssetActivity(BaseModel):
    aud_spent: float
    buy_count: int
    current_value_aud: float


class KrakenFYActivity(BaseModel):
    total_aud_invested: float
    total_buys: int
    per_asset: dict[str, KrakenAssetActivity]


class FYOverview(BaseModel):
    financial_year: str
    income_total_aud: float
    tax_paid_total_aud: float
    deductibles_total_aud: float
    kraken_activity: KrakenFYActivity
