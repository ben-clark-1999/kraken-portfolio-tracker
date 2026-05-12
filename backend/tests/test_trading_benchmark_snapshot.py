from datetime import datetime, timezone
from decimal import Decimal

from backend.services.trading.benchmark_snapshot import (
    compute_btc_hodl_equity, compute_alt_basket_equity,
    next_rebalance_due_at, AltBasketState,
)


T0 = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)


def test_btc_hodl_equity_scales_with_btc_price_relative_to_t0():
    eq = compute_btc_hodl_equity(
        starting_balance_aud=Decimal("1000"),
        btc_price_at_start=Decimal("90000"),
        btc_price_now=Decimal("108000"),
    )
    # 20% rise → equity 1200
    assert eq == Decimal("1200")


def test_alt_basket_initialises_equal_weight_at_t0():
    state = AltBasketState.initialise(
        starting_balance_aud=Decimal("1000"),
        initial_prices={"ETH/AUD": Decimal("3000"), "LINK/AUD": Decimal("15"),
                        "ADA/AUD": Decimal("0.40"), "SOL/AUD": Decimal("100")},
        t0=T0,
    )
    # Each asset gets 250 AUD at t0.
    assert state.units["ETH/AUD"] == Decimal("250") / Decimal("3000")


def test_alt_basket_equity_updates_with_prices():
    state = AltBasketState.initialise(
        starting_balance_aud=Decimal("1000"),
        initial_prices={"ETH/AUD": Decimal("3000"), "LINK/AUD": Decimal("15"),
                        "ADA/AUD": Decimal("0.40"), "SOL/AUD": Decimal("100")},
        t0=T0,
    )
    # ETH +20%, others flat → +5% of total (since each is 25% weight).
    eq = compute_alt_basket_equity(
        state=state,
        current_prices={"ETH/AUD": Decimal("3600"), "LINK/AUD": Decimal("15"),
                        "ADA/AUD": Decimal("0.40"), "SOL/AUD": Decimal("100")},
    )
    assert eq == Decimal("1050")


def test_monthly_rebalance_is_due_at_first_of_next_month():
    last = datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
    nxt = next_rebalance_due_at(last)
    assert nxt == datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc)
