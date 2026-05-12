from decimal import Decimal

from backend.services.trading.fees import (
    FeeSchedule, KRAKEN_PRO_SPOT_TIER_1, apply_fee,
)


def test_default_schedule_is_lowest_kraken_tier():
    # Spec decision-log row 13: 0.25% maker / 0.40% taker
    assert KRAKEN_PRO_SPOT_TIER_1.maker_bps == 25
    assert KRAKEN_PRO_SPOT_TIER_1.taker_bps == 40


def test_apply_fee_taker_on_aud_50_at_0_40pct():
    # qty=1, price=50 → notional 50; 0.40% of 50 = 0.20
    fee = apply_fee(qty=Decimal("1"), price=Decimal("50"),
                    role="taker", schedule=KRAKEN_PRO_SPOT_TIER_1)
    assert fee == Decimal("0.20")


def test_apply_fee_maker_on_aud_50_at_0_25pct():
    fee = apply_fee(qty=Decimal("1"), price=Decimal("50"),
                    role="maker", schedule=KRAKEN_PRO_SPOT_TIER_1)
    assert fee == Decimal("0.125")


def test_apply_fee_zero_qty_zero_fee():
    fee = apply_fee(qty=Decimal("0"), price=Decimal("100"),
                    role="taker", schedule=KRAKEN_PRO_SPOT_TIER_1)
    assert fee == Decimal("0")


def test_custom_schedule():
    sch = FeeSchedule(maker_bps=10, taker_bps=20)
    fee = apply_fee(qty=Decimal("2"), price=Decimal("100"),
                    role="taker", schedule=sch)
    # notional 200, 20bps = 0.4
    assert fee == Decimal("0.4")
