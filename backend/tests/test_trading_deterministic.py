from decimal import Decimal

from backend.models.trading import DeterministicConfig
from backend.services.trading.deterministic import compute_rebalance_orders


def _dca_config():
    return DeterministicConfig(
        cadence_cron="0 9 */14 * *", tz="Australia/Sydney",
        allocations={
            "ETH/AUD": Decimal("0.50"),
            "SOL/AUD": Decimal("0.25"),
            "LINK/AUD": Decimal("0.15"),
            "ADA/AUD": Decimal("0.10"),
        },
    )


def _mids():
    return {
        "ETH/AUD": Decimal("3000"),
        "SOL/AUD": Decimal("100"),
        "LINK/AUD": Decimal("15"),
        "ADA/AUD": Decimal("0.40"),
    }


def test_initial_buy_allocates_per_weights_using_total_starting_aud():
    orders = compute_rebalance_orders(
        positions_aud={"AUD": Decimal("1000")},
        target_weights=_dca_config().allocations,
        starting_balance_aud=Decimal("1000"),
        mids=_mids(),
    )
    by_pair = {o.pair: o for o in orders}
    # Sanity: AUD totals to ~ 1000 across the 4 buys.
    total = sum(o.notional_aud for o in orders)
    assert total <= Decimal("1000")
    # 50% of starting capital goes to ETH/AUD on first run.
    assert by_pair["ETH/AUD"].notional_aud == Decimal("500.00")
    assert by_pair["SOL/AUD"].notional_aud == Decimal("250.00")
    assert by_pair["LINK/AUD"].notional_aud == Decimal("150.00")
    assert by_pair["ADA/AUD"].notional_aud == Decimal("100.00")
    for o in orders:
        assert o.side == "buy"


def test_rebalance_after_drift_increases_underweight_decreases_over():
    # ETH up 33%, others flat → ETH position now overweight, others under.
    positions = {
        "AUD": Decimal("0"),     # used up at first buy
        "ETH": Decimal("665"),    # was 500, +33%
        "SOL": Decimal("250"),
        "LINK": Decimal("150"),
        "ADA": Decimal("100"),
    }
    orders = compute_rebalance_orders(
        positions_aud=positions,
        target_weights=_dca_config().allocations,
        starting_balance_aud=Decimal("1000"),
        mids=_mids(),
    )
    # Total equity 1165; ETH target 50% = 582.5; current 665 → sell ~82.5
    eth = next(o for o in orders if o.pair == "ETH/AUD")
    assert eth.side == "sell"
    # Others should be buys (they're underweight relative to new equity).
    for o in orders:
        if o.pair != "ETH/AUD":
            assert o.side == "buy"


def test_zero_drift_produces_no_orders():
    positions = {
        "AUD": Decimal("0"),
        "ETH": Decimal("500"), "SOL": Decimal("250"),
        "LINK": Decimal("150"), "ADA": Decimal("100"),
    }
    orders = compute_rebalance_orders(
        positions_aud=positions,
        target_weights=_dca_config().allocations,
        starting_balance_aud=Decimal("1000"),
        mids=_mids(),
    )
    # All trades within ±0.5 AUD threshold → skipped.
    assert orders == []
