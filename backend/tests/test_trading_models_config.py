from decimal import Decimal

import pytest

from backend.models.trading import DeterministicConfig


def test_default_mode_is_rebalance_and_allocations_validated():
    cfg = DeterministicConfig(
        cadence_cron="0 9 * * 1",
        allocations={"ETH/AUD": Decimal("0.5"), "SOL/AUD": Decimal("0.5")},
    )
    assert cfg.mode == "rebalance"


def test_allocations_must_sum_to_one_when_present():
    with pytest.raises(ValueError):
        DeterministicConfig(
            cadence_cron="0 9 * * 1",
            allocations={"ETH/AUD": Decimal("0.5"), "SOL/AUD": Decimal("0.4")},
        )


def test_rule_mode_allows_empty_allocations_with_universe():
    cfg = DeterministicConfig(
        cadence_cron="0 9 * * *",
        mode="trend_rule",
        universe=["ETH/AUD", "SOL/AUD"],
        min_move_pct=Decimal("1.5"),
    )
    assert cfg.allocations == {}
    assert cfg.universe == ["ETH/AUD", "SOL/AUD"]
    assert cfg.min_move_pct == Decimal("1.5")


def test_dca_mode_carries_num_buys():
    cfg = DeterministicConfig(
        cadence_cron="0 9 * * 1",
        mode="dca",
        num_buys=12,
        allocations={"ETH/AUD": Decimal("0.5"), "SOL/AUD": Decimal("0.5")},
    )
    assert cfg.num_buys == 12


def test_mean_reversion_defaults():
    cfg = DeterministicConfig(
        cadence_cron="0 9 * * *",
        mode="mean_reversion_rule",
        universe=["ETH/AUD"],
    )
    assert cfg.entry_z == Decimal("-2")
    assert cfg.exit_z == Decimal("0")
