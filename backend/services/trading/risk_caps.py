"""Risk-cap pre-check. Run before every order.

See spec §5.2 (executor pre-check) and §10.2 (property-based test contract).
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Literal

from backend.models.trading import RiskCaps


CAP_NAMES = (
    "MAX_ORDER_AUD",
    "BELOW_MIN_ORDER",
    "MAX_SINGLE_ASSET_PCT",
    "MAX_TOTAL_CRYPTO_EXPOSURE_PCT",
    "DAILY_LOSS_CAP_AUD",
    "MAX_DRAWDOWN_PCT",
    "PAIR_NOT_ALLOWED",
    "INSUFFICIENT_BALANCE",
)


def _asset_of(pair: str) -> str:
    return pair.split("/", 1)[0]


@dataclass
class OrderIntent:
    pair: str
    side: Literal["buy", "sell"]
    notional_aud: Decimal


@dataclass
class PortfolioState:
    cash_aud: Decimal
    positions: dict[str, Decimal] = field(default_factory=dict)   # asset → AUD value
    session_loss_aud: Decimal = Decimal("0")
    drawdown_pct: Decimal = Decimal("0")

    @property
    def total_crypto_aud(self) -> Decimal:
        return sum(self.positions.values(), Decimal("0"))

    @property
    def equity_aud(self) -> Decimal:
        return self.cash_aud + self.total_crypto_aud

    def simulate_fill(self, order: OrderIntent) -> "PortfolioState":
        new = replace(self, positions=dict(self.positions))
        asset = _asset_of(order.pair)
        if order.side == "buy":
            new.cash_aud -= order.notional_aud
            new.positions[asset] = new.positions.get(asset, Decimal("0")) + order.notional_aud
        else:
            # A sell can only realise cash up to the value actually held —
            # selling an asset you don't own is a no-op, not free cash. (This
            # keeps acceptance monotonic in notional: a smaller sell is never
            # riskier than a larger one.)
            held = new.positions.get(asset, Decimal("0"))
            realized = min(order.notional_aud, held) if held > Decimal("0") else Decimal("0")
            new.cash_aud += realized
            new.positions[asset] = held - realized
        return new

    def satisfies(self, caps: RiskCaps) -> bool:
        eq = self.equity_aud
        if eq <= 0:
            return False
        for asset, val in self.positions.items():
            if val < 0:
                return False
            if (val / eq) * Decimal("100") > caps.max_single_asset_pct + Decimal("0.001"):
                return False
        if (self.total_crypto_aud / eq) * Decimal("100") > caps.max_total_crypto_exposure_pct + Decimal("0.001"):
            return False
        return True


@dataclass
class PrecheckResult:
    accepted: bool
    reject_reason: str | None = None


def risk_cap_precheck(
    *, state: PortfolioState, order: OrderIntent, caps: RiskCaps,
    min_order_aud: Decimal | None = None,
) -> PrecheckResult:
    # 1. Pair allowed?
    if order.pair not in caps.allowed_pairs:
        return PrecheckResult(False, "PAIR_NOT_ALLOWED")

    # 1b. Order at least the exchange minimum? `min_order_aud` is the pair's
    #     Kraken floor already expressed in AUD — max(costmin, ordermin*price)
    #     — so this one comparison enforces BOTH minimums, buy or sell. When
    #     None (e.g. property tests, or minimums unavailable) the gate is off.
    if min_order_aud is not None and order.notional_aud < min_order_aud:
        return PrecheckResult(False, "BELOW_MIN_ORDER")

    # 2. Order AUD within max_order_aud?
    if order.notional_aud > caps.max_order_aud:
        return PrecheckResult(False, "MAX_ORDER_AUD")

    # 3. Sufficient cash for a buy?
    if order.side == "buy" and order.notional_aud > state.cash_aud:
        return PrecheckResult(False, "INSUFFICIENT_BALANCE")

    # 4. Session loss already at/over cap?
    if state.session_loss_aud >= caps.daily_loss_cap_aud:
        return PrecheckResult(False, "DAILY_LOSS_CAP_AUD")

    # 5. Drawdown already over cap?
    if state.drawdown_pct >= caps.max_drawdown_pct_before_pause:
        return PrecheckResult(False, "MAX_DRAWDOWN_PCT")

    # 6. Post-fill: per-asset cap.
    post = state.simulate_fill(order)
    eq = post.equity_aud
    if eq <= 0:
        return PrecheckResult(False, "INSUFFICIENT_BALANCE")
    for asset, val in post.positions.items():
        if (val / eq) * Decimal("100") > caps.max_single_asset_pct + Decimal("0.001"):
            return PrecheckResult(False, "MAX_SINGLE_ASSET_PCT")

    # 7. Post-fill: total crypto cap.
    if (post.total_crypto_aud / eq) * Decimal("100") > caps.max_total_crypto_exposure_pct + Decimal("0.001"):
        return PrecheckResult(False, "MAX_TOTAL_CRYPTO_EXPOSURE_PCT")

    return PrecheckResult(True)
