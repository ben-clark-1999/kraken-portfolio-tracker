from backend.scripts.seed_strategies import (
    _RISK_CAPS_DEFAULT, _KILL_CRITERIA_DEFAULT,
)


def test_no_allocation_limits():
    assert _RISK_CAPS_DEFAULT["max_single_asset_pct"] == 100
    assert _RISK_CAPS_DEFAULT["max_total_crypto_exposure_pct"] == 100


def test_per_order_cap_retained_as_sanity_ceiling():
    assert _RISK_CAPS_DEFAULT["max_order_aud"] == 250


def test_no_auto_pause_for_anyone():
    assert _KILL_CRITERIA_DEFAULT["auto_pause_when"] == []


def test_loss_and_drawdown_caps_set_so_they_cannot_fire():
    assert _RISK_CAPS_DEFAULT["daily_loss_cap_aud"] >= 1_000_000
    assert _RISK_CAPS_DEFAULT["max_drawdown_pct_before_pause"] >= 100
