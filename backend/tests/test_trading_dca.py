from decimal import Decimal

from backend.services.trading.deterministic import compute_dca_orders


WEIGHTS = {
    "ETH/AUD": Decimal("0.50"),
    "SOL/AUD": Decimal("0.25"),
    "LINK/AUD": Decimal("0.15"),
    "ADA/AUD": Decimal("0.10"),
}


def test_full_slice_split_by_weight():
    # slice_total = 1000/12 ≈ 83.333...
    orders = compute_dca_orders(
        cash_aud=Decimal("1000"),
        slice_total=Decimal("1000") / Decimal("12"),
        weights=WEIGHTS,
    )
    by_pair = {o.pair: o for o in orders}
    assert all(o.side == "buy" for o in orders)
    # ETH = 50% of the slice ≈ 41.67
    assert by_pair["ETH/AUD"].notional_aud == (Decimal("1000") / Decimal("12")) * Decimal("0.50")
    # The whole slice is spent.
    assert sum(o.notional_aud for o in orders) == Decimal("1000") / Decimal("12")


def test_final_partial_slice_spends_remaining_cash():
    # Less than a full slice left → spend exactly what remains.
    remaining = Decimal("40")
    orders = compute_dca_orders(
        cash_aud=remaining,
        slice_total=Decimal("1000") / Decimal("12"),
        weights=WEIGHTS,
    )
    assert sum(o.notional_aud for o in orders) == remaining


def test_cash_exhausted_stops_buying():
    orders = compute_dca_orders(
        cash_aud=Decimal("0.50"),  # below the dust floor
        slice_total=Decimal("1000") / Decimal("12"),
        weights=WEIGHTS,
    )
    assert orders == []


def test_per_pair_buys_stay_below_per_order_cap():
    # Largest single buy is ETH at 50% of an ~83 slice ≈ 41.67 << 250.
    orders = compute_dca_orders(
        cash_aud=Decimal("1000"),
        slice_total=Decimal("1000") / Decimal("12"),
        weights=WEIGHTS,
    )
    assert all(o.notional_aud < Decimal("250") for o in orders)
