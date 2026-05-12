from decimal import Decimal
from unittest.mock import patch

from backend.services.trading.min_order import (
    MinOrderDecision, evaluate_min_order_for_pair,
    filter_allowed_pairs_by_min_order,
)


def _fake_asset_pairs():
    # Mirrors the live shape but tiny.
    return {
        "ETH/AUD":  {"ordermin": Decimal("0.001"), "costmin": Decimal("1")},
        "LINK/AUD": {"ordermin": Decimal("0.55"),  "costmin": Decimal("1")},
        "ADA/AUD":  {"ordermin": Decimal("20"),    "costmin": Decimal("1")},
        "SOL/AUD":  {"ordermin": Decimal("0.02"),  "costmin": Decimal("1")},
    }


def _fake_prices():
    return {
        "ETH/AUD":  Decimal("3196.60"),
        "LINK/AUD": Decimal("14.58"),
        "ADA/AUD":  Decimal("0.385"),
        "SOL/AUD":  Decimal("133.23"),
    }


def test_eth_aud_passes_at_aud_1k_capital():
    res = evaluate_min_order_for_pair(
        pair="ETH/AUD",
        ordermin=Decimal("0.001"),
        current_price=Decimal("3196.60"),
        max_position_aud=Decimal("300"),
    )
    # 0.001 * 3196.60 = 3.20; threshold = 0.05 * 300 = 15
    assert res.passes
    assert res.min_order_aud == Decimal("3.1966")


def test_pair_fails_when_min_order_exceeds_threshold():
    res = evaluate_min_order_for_pair(
        pair="X/AUD",
        ordermin=Decimal("1"),
        current_price=Decimal("100"),    # min order = AUD 100
        max_position_aud=Decimal("300"),  # threshold = AUD 15
    )
    assert not res.passes
    assert "exceeds threshold" in res.reason


def test_filter_allowed_pairs_all_pass_at_v1_defaults():
    pairs = ["ETH/AUD", "LINK/AUD", "ADA/AUD", "SOL/AUD"]
    with patch("backend.services.trading.min_order.fetch_asset_pairs",
               return_value=_fake_asset_pairs()), \
         patch("backend.services.trading.min_order.fetch_last_prices",
               return_value=_fake_prices()):
        kept, dropped = filter_allowed_pairs_by_min_order(
            pairs=pairs, max_position_aud=Decimal("300"),
        )
    assert kept == pairs
    assert dropped == []


def test_filter_drops_pair_when_threshold_too_tight():
    pairs = ["ETH/AUD", "LINK/AUD"]
    # max_position_aud = 100 → threshold AUD 5.00.
    # ETH min order = 0.001 * 3196.60 = 3.20 → 3.20 < 5.00 → passes (kept).
    # LINK min order = 0.55 * 14.58 = 8.02 → 8.02 > 5.00 → fails (dropped).
    with patch("backend.services.trading.min_order.fetch_asset_pairs",
               return_value=_fake_asset_pairs()), \
         patch("backend.services.trading.min_order.fetch_last_prices",
               return_value=_fake_prices()):
        kept, dropped = filter_allowed_pairs_by_min_order(
            pairs=pairs, max_position_aud=Decimal("100"),
        )
    assert "LINK/AUD" in dropped
    assert "ETH/AUD" in kept


def test_filter_drops_both_when_threshold_extreme():
    pairs = ["ETH/AUD", "LINK/AUD"]
    with patch("backend.services.trading.min_order.fetch_asset_pairs",
               return_value=_fake_asset_pairs()), \
         patch("backend.services.trading.min_order.fetch_last_prices",
               return_value=_fake_prices()):
        kept, dropped = filter_allowed_pairs_by_min_order(
            pairs=pairs, max_position_aud=Decimal("30"),
        )
    assert dropped == ["ETH/AUD", "LINK/AUD"]
    assert kept == []
