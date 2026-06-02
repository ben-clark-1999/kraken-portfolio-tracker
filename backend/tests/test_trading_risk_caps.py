"""Property-based tests for risk_cap_precheck.

See spec §10.2.
"""
from decimal import Decimal

from hypothesis import given, strategies as st, assume, settings

from backend.models.trading import RiskCaps
from backend.services.trading.risk_caps import (
    PortfolioState, OrderIntent, risk_cap_precheck, CAP_NAMES,
)


def _state(cash=Decimal("1000"), positions=None):
    return PortfolioState(
        cash_aud=cash,
        positions=positions or {},   # asset → AUD value
        session_loss_aud=Decimal("0"),
        drawdown_pct=Decimal("0"),
    )


def _order(pair="ETH/AUD", side="buy", aud=Decimal("100")):
    return OrderIntent(pair=pair, side=side, notional_aud=aud)


# ── Example-based smoke tests ───────────────────────────────────

def test_simple_buy_within_caps_accepted():
    res = risk_cap_precheck(state=_state(), order=_order(),
                            caps=RiskCaps())
    assert res.accepted


def test_buy_exceeding_max_order_aud_rejected():
    res = risk_cap_precheck(
        state=_state(), order=_order(aud=Decimal("300")),
        caps=RiskCaps(),
    )
    assert not res.accepted
    assert res.reject_reason == "MAX_ORDER_AUD"


def test_buy_exceeding_single_asset_cap_rejected():
    # 30% of 1000 = 300; existing 250 ETH + 100 new = 350 > cap
    state = _state(cash=Decimal("750"), positions={"ETH": Decimal("250")})
    res = risk_cap_precheck(state=state, order=_order(aud=Decimal("100")),
                            caps=RiskCaps())
    assert not res.accepted
    assert res.reject_reason == "MAX_SINGLE_ASSET_PCT"


def test_total_crypto_cap_rejects_when_post_fill_exceeds():
    # 60% of 1000 = 600; existing crypto 550 + 100 new = 650 > cap
    state = _state(cash=Decimal("450"),
                   positions={"ETH": Decimal("200"), "SOL": Decimal("200"),
                              "LINK": Decimal("150")})
    res = risk_cap_precheck(state=state, order=_order(aud=Decimal("100")),
                            caps=RiskCaps())
    assert not res.accepted
    assert res.reject_reason == "MAX_TOTAL_CRYPTO_EXPOSURE_PCT"


# ── Minimum-order gate (Kraken ordermin / costmin, in AUD) ──────

def test_order_below_min_order_aud_rejected_buy_and_sell():
    # An order whose AUD notional is below the pair's minimum is rejected
    # regardless of side — you can't place a sub-minimum buy OR sell.
    state = _state(positions={"ETH": Decimal("100")})
    for side in ("buy", "sell"):
        res = risk_cap_precheck(
            state=state, order=_order(side=side, aud=Decimal("0.50")),
            caps=RiskCaps(), min_order_aud=Decimal("5"),
        )
        assert not res.accepted, side
        assert res.reject_reason == "BELOW_MIN_ORDER", side


def test_order_at_min_order_aud_passes_min_gate():
    res = risk_cap_precheck(
        state=_state(), order=_order(aud=Decimal("5")),
        caps=RiskCaps(), min_order_aud=Decimal("5"),
    )
    assert res.accepted


def test_no_min_order_aud_means_no_min_gate():
    # Default (no minimum supplied): a tiny order is NOT rejected for size.
    res = risk_cap_precheck(
        state=_state(), order=_order(aud=Decimal("0.01")),
        caps=RiskCaps(),
    )
    assert res.accepted


def test_daily_loss_cap_blocks_further_orders():
    state = _state()
    state.session_loss_aud = Decimal("100.01")
    res = risk_cap_precheck(state=state, order=_order(), caps=RiskCaps())
    assert not res.accepted
    assert res.reject_reason == "DAILY_LOSS_CAP_AUD"


def test_drawdown_cap_blocks():
    state = _state()
    state.drawdown_pct = Decimal("25.01")
    res = risk_cap_precheck(state=state, order=_order(), caps=RiskCaps())
    assert not res.accepted
    assert res.reject_reason == "MAX_DRAWDOWN_PCT"


def test_pair_not_in_allowed_list_rejected():
    res = risk_cap_precheck(
        state=_state(), order=_order(pair="DOGE/AUD"),
        caps=RiskCaps(),
    )
    assert not res.accepted
    assert res.reject_reason == "PAIR_NOT_ALLOWED"


# ── Property-based tests (spec §10.2) ───────────────────────────

decimals_pos = st.decimals(min_value=Decimal("0"), max_value=Decimal("10000"),
                           places=2, allow_nan=False, allow_infinity=False)

def _portfolios():
    return st.builds(
        lambda cash, eth, link, ada, sol, loss, dd: PortfolioState(
            cash_aud=cash,
            positions={"ETH": eth, "LINK": link, "ADA": ada, "SOL": sol},
            session_loss_aud=loss,
            drawdown_pct=dd,
        ),
        cash=decimals_pos,
        eth=decimals_pos, link=decimals_pos, ada=decimals_pos, sol=decimals_pos,
        loss=st.decimals(min_value=Decimal("0"), max_value=Decimal("500"), places=2),
        dd=st.decimals(min_value=Decimal("0"), max_value=Decimal("50"), places=2),
    )

def _orders():
    return st.builds(
        OrderIntent,
        pair=st.sampled_from(["ETH/AUD", "LINK/AUD", "ADA/AUD", "SOL/AUD"]),
        side=st.sampled_from(["buy", "sell"]),
        notional_aud=st.decimals(min_value=Decimal("0"), max_value=Decimal("2000"),
                                 places=2),
    )


@given(portfolio=_portfolios(), order=_orders())
@settings(max_examples=200)
def test_accept_implies_post_fill_satisfies_all_caps(portfolio, order):
    res = risk_cap_precheck(state=portfolio, order=order, caps=RiskCaps())
    if res.accepted:
        # Apply hypothetical fill and assert no cap is violated.
        post = portfolio.simulate_fill(order)
        assert post.satisfies(RiskCaps())


@given(portfolio=_portfolios(), order=_orders())
@settings(max_examples=200)
def test_reject_reason_names_a_cap(portfolio, order):
    res = risk_cap_precheck(state=portfolio, order=order, caps=RiskCaps())
    if not res.accepted:
        assert res.reject_reason in CAP_NAMES


@given(portfolio=_portfolios(), order=_orders())
@settings(max_examples=200)
def test_pre_check_monotonic_in_qty(portfolio, order):
    """If accepted at notional N, also accepted at any 0 < n < N (same pair/side)."""
    assume(order.notional_aud > Decimal("0"))
    res = risk_cap_precheck(state=portfolio, order=order, caps=RiskCaps())
    if res.accepted:
        smaller = OrderIntent(pair=order.pair, side=order.side,
                              notional_aud=order.notional_aud / 2)
        assert risk_cap_precheck(state=portfolio, order=smaller,
                                 caps=RiskCaps()).accepted
