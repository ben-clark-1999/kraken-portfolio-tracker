from decimal import Decimal

from backend.services.trading.deterministic import TargetOrder, split_order


def test_order_under_cap_is_unchanged():
    o = TargetOrder(pair="ETH/AUD", side="buy", notional_aud=Decimal("200"))
    out = split_order(order=o, max_order_aud=Decimal("250"))
    assert len(out) == 1
    assert out[0].notional_aud == Decimal("200")


def test_order_over_cap_splits_into_equal_chunks_summing_to_total():
    o = TargetOrder(pair="ETH/AUD", side="buy", notional_aud=Decimal("330"))
    out = split_order(order=o, max_order_aud=Decimal("250"))
    assert len(out) == 2
    assert all(c.notional_aud <= Decimal("250") for c in out)
    assert all(c.pair == "ETH/AUD" and c.side == "buy" for c in out)
    assert sum(c.notional_aud for c in out) == Decimal("330")


def test_exact_multiple_of_cap():
    o = TargetOrder(pair="SOL/AUD", side="sell", notional_aud=Decimal("500"))
    out = split_order(order=o, max_order_aud=Decimal("250"))
    assert len(out) == 2
    assert all(c.notional_aud == Decimal("250") for c in out)


def test_large_order_splits_into_three():
    o = TargetOrder(pair="ETH/AUD", side="buy", notional_aud=Decimal("700"))
    out = split_order(order=o, max_order_aud=Decimal("250"))
    assert len(out) == 3
    assert sum(c.notional_aud for c in out) == Decimal("700")
    assert all(c.notional_aud <= Decimal("250") for c in out)
