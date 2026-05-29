"""Pydantic models for the paper-trading sandbox.

See docs/superpowers/specs/2026-05-12-paper-trading-sandbox-design.md §4.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, TypeAdapter, field_validator


# ─────────────────────────── Order book ───────────────────────────

class OrderBookLevel(BaseModel):
    price: Decimal
    qty: Decimal


class OrderBookSnapshot(BaseModel):
    pair: str
    asks: list[OrderBookLevel]   # ascending
    bids: list[OrderBookLevel]   # descending
    checksum: str
    ts: datetime


# ─────────────────────────── Orders & fills ───────────────────────

OrderSide = Literal["buy", "sell"]
OrderType = Literal["market", "limit"]
OrderStatus = Literal["pending", "filled", "partial", "rejected", "cancelled", "expired"]
FeeRole = Literal["maker", "taker"]


class Fill(BaseModel):
    qty: Decimal
    price: Decimal
    fee_aud: Decimal
    fee_role: FeeRole
    book_state_hash: str | None = None
    filled_at: datetime


class OrderResult(BaseModel):
    order_id: UUID | str
    status: OrderStatus
    fills: list[Fill] = []
    reject_reason: str | None = None


class OrderRow(BaseModel):
    id: UUID
    strategy_id: UUID
    idempotency_key: str
    pair: str
    side: OrderSide
    type: OrderType
    qty: Decimal
    limit_price: Decimal | None = None
    expires_at: datetime | None = None
    status: OrderStatus
    reject_reason: str | None = None
    decided_by: UUID | None = None
    created_at: datetime


# ─────────────────────────── Bus events ───────────────────────────

class TickEvent(BaseModel):
    type: Literal["tick"] = "tick"
    pair: str
    price: Decimal
    ts: datetime


class BookUpdateEvent(BaseModel):
    type: Literal["book_update"] = "book_update"
    pair: str
    snapshot: OrderBookSnapshot
    ts: datetime


class CronTriggerEvent(BaseModel):
    type: Literal["cron"] = "cron"
    expr: str
    ts: datetime


class IntervalTriggerEvent(BaseModel):
    type: Literal["interval"] = "interval"
    minutes: int
    ts: datetime


class PriceBreakoutEvent(BaseModel):
    type: Literal["price_breakout"] = "price_breakout"
    pair: str
    direction: Literal["up", "down"]
    move_pct: Decimal
    lookback_bars: int
    ts: datetime


class PriceStretchEvent(BaseModel):
    type: Literal["price_stretch"] = "price_stretch"
    pair: str
    direction: Literal["above", "below"]
    stdev_distance: Decimal
    ts: datetime


class OrderFilledEvent(BaseModel):
    type: Literal["order_filled"] = "order_filled"
    order_id: UUID
    strategy_id: UUID
    ts: datetime


class DrawdownEvent(BaseModel):
    type: Literal["drawdown"] = "drawdown"
    strategy_id: UUID
    session_pct: Decimal
    ts: datetime


TriggerEvent = Annotated[
    CronTriggerEvent | IntervalTriggerEvent | PriceBreakoutEvent
    | PriceStretchEvent | OrderFilledEvent | DrawdownEvent
    | TickEvent | BookUpdateEvent,
    Field(discriminator="type"),
]

_trigger_event_adapter: TypeAdapter[TriggerEvent] = TypeAdapter(TriggerEvent)


def validate_trigger_event(data: object) -> TriggerEvent:
    """Parse a dict/JSON into the appropriate concrete TriggerEvent subtype."""
    return _trigger_event_adapter.validate_python(data)


# ─────────────────────────── Configs ──────────────────────────────

class RiskCaps(BaseModel):
    max_single_asset_pct: Decimal = Decimal("30")
    max_total_crypto_exposure_pct: Decimal = Decimal("60")
    max_order_aud: Decimal = Decimal("250")
    daily_loss_cap_aud: Decimal = Decimal("100")  # FIXED, not moving; see spec decision-log row 22
    max_drawdown_pct_before_pause: Decimal = Decimal("25")
    allowed_pairs: list[str] = ["ETH/AUD", "LINK/AUD", "ADA/AUD", "SOL/AUD"]


class KillCriterion(BaseModel):
    metric: str   # 'drawdown_pct' | 'daily_loss_aud' | 'trailing_30d_sharpe'
    op: Literal[">=", ">", "<=", "<", "=="]
    value: Decimal


class KillCriteria(BaseModel):
    auto_pause_when: list[KillCriterion] = []


class DeterministicConfig(BaseModel):
    cadence_cron: str
    tz: str = "Australia/Sydney"
    # 'rebalance' = original target-weight rebalancer (kept for back-compat).
    # 'dca'       = fixed-slice weekly dollar-cost averaging.
    # 'trend_rule'/'mean_reversion_rule' = matched-twin control strategies.
    mode: Literal["rebalance", "dca", "trend_rule", "mean_reversion_rule"] = "rebalance"
    # Used by 'rebalance' and 'dca'. Empty for rule modes (targets computed
    # at fire time). When present, must sum to 1.0.
    allocations: dict[str, Decimal] = {}
    # 'dca' only: number of equal slices the starting balance is split into.
    num_buys: int | None = None
    # Rule modes only: the pairs the rule watches.
    universe: list[str] = []
    # 'trend_rule' only: breakout threshold off the trailing 24h high/low.
    min_move_pct: Decimal = Decimal("1.5")
    # 'mean_reversion_rule' only: z-score entry/exit cutoffs.
    entry_z: Decimal = Decimal("-2")
    exit_z: Decimal = Decimal("0")

    @field_validator("allocations")
    @classmethod
    def _weights_sum_to_one(cls, v: dict[str, Decimal]) -> dict[str, Decimal]:
        if not v:
            return v
        total = sum(v.values())
        if abs(total - Decimal("1")) > Decimal("0.0001"):
            raise ValueError(f"allocations must sum to 1.0, got {total}")
        return v


class StrategyRow(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    execution_mode: Literal["llm_agent", "deterministic"]
    persona_key: str | None = None
    deterministic_config: DeterministicConfig | None = None
    starting_balance_aud: Decimal = Decimal("1000")
    trigger_config: dict = {}
    risk_caps: RiskCaps = RiskCaps()
    kill_criteria: KillCriteria = KillCriteria()
    model_preference: str | None = None
    status: Literal["active", "paused", "archived"] = "active"
    dry_run: bool = False
    notify_enabled: bool = False
    persona_prompt_stable_since: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ─────────────────────────── Decisions ────────────────────────────

class AgentDecisionRow(BaseModel):
    id: UUID
    strategy_id: UUID
    execution_mode: str
    trigger_event: dict
    input_snapshot: dict
    persona_prompt_hash: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_aud: Decimal = Decimal("0")
    tool_calls: list[dict] = []
    agent_output: str | None = None
    latency_ms: int | None = None
    error: str | None = None
    created_at: datetime
