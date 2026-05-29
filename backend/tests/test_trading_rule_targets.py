from decimal import Decimal

from backend.services.trading.deterministic import compute_rule_targets


UNIVERSE = ["ETH/AUD", "SOL/AUD", "LINK/AUD", "ADA/AUD"]


def test_no_flip_returns_none():
    # Already long ETH+SOL, signals say keep them → no trades.
    out = compute_rule_targets(
        enter=set(), exit_=set(),
        universe=UNIVERSE, held={"ETH/AUD", "SOL/AUD"},
    )
    assert out is None


def test_entering_a_new_coin_equal_weights_the_new_set():
    out = compute_rule_targets(
        enter={"LINK/AUD"}, exit_=set(),
        universe=UNIVERSE, held={"ETH/AUD", "SOL/AUD"},
    )
    # New held set = {ETH, SOL, LINK} → 1/3 each, 0 for ADA.
    assert out["ETH/AUD"] == Decimal("1") / Decimal("3")
    assert out["SOL/AUD"] == Decimal("1") / Decimal("3")
    assert out["LINK/AUD"] == Decimal("1") / Decimal("3")
    assert out["ADA/AUD"] == Decimal("0")


def test_exiting_a_coin_drops_it_to_zero_and_reweights_rest():
    out = compute_rule_targets(
        enter=set(), exit_={"SOL/AUD"},
        universe=UNIVERSE, held={"ETH/AUD", "SOL/AUD"},
    )
    assert out["ETH/AUD"] == Decimal("1")
    assert out["SOL/AUD"] == Decimal("0")


def test_all_exit_goes_fully_to_cash():
    out = compute_rule_targets(
        enter=set(), exit_={"ETH/AUD"},
        universe=UNIVERSE, held={"ETH/AUD"},
    )
    assert all(out[p] == Decimal("0") for p in UNIVERSE)


def test_full_universe_keys_always_present():
    out = compute_rule_targets(
        enter={"ADA/AUD"}, exit_=set(),
        universe=UNIVERSE, held=set(),
    )
    assert set(out.keys()) == set(UNIVERSE)
