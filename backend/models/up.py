"""Pydantic models for UP Bank API resources."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel


class UpAccount(BaseModel):
    id: str
    display_name: str
    account_type: str  # TRANSACTIONAL | SAVER | HOME_LOAN
    ownership_type: str  # INDIVIDUAL | JOINT
    balance_value: float  # AUD, signed (positive for assets, negative for HOME_LOAN)
    balance_currency: str = "AUD"
    created_at: datetime


class UpCategory(BaseModel):
    id: str
    name: str
    parent_id: str | None = None


class UpTransaction(BaseModel):
    id: str
    account_id: str
    status: str  # HELD | SETTLED
    description: str
    message: str | None = None
    raw_text: str | None = None
    amount_value: float  # signed; negative = outflow
    amount_currency: str = "AUD"
    category_id: str | None = None
    parent_category_id: str | None = None
    created_at: datetime
    settled_at: datetime | None = None


class RecurringCharge(BaseModel):
    """A recurring outflow subscription detected from the transaction log."""
    name: str
    sample_description: str
    cadence: Literal["weekly", "fortnightly", "monthly", "yearly"]
    median_amount: float  # positive — outflow magnitude
    last_charged_at: datetime
    next_expected_at: datetime
    occurrence_count: int
    monthly_equivalent: float  # cadence-normalised cost for sorting + aggregation
