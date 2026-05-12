"""Boundary tests for kill-criteria evaluator (spec §10.3)."""
from dataclasses import dataclass
from decimal import Decimal

from backend.models.trading import KillCriteria, KillCriterion
from backend.services.trading.kill_criteria import (
    KillSnapshot, evaluate_kill_criteria,
)


def _crit(metric, op, value):
    return KillCriterion(metric=metric, op=op, value=Decimal(value))


# ── drawdown_pct boundary ───────────────────────────────────────

def test_drawdown_fires_at_exactly_threshold():
    snap = KillSnapshot(drawdown_pct=Decimal("25"),
                        daily_loss_aud=Decimal("0"),
                        trailing_30d_sharpe=Decimal("1"))
    res = evaluate_kill_criteria(
        snapshot=snap,
        criteria=KillCriteria(auto_pause_when=[_crit("drawdown_pct", ">=", "25")]),
    )
    assert res.fires
    assert res.matched_metric == "drawdown_pct"


def test_drawdown_does_not_fire_just_below():
    snap = KillSnapshot(drawdown_pct=Decimal("24.99"),
                        daily_loss_aud=Decimal("0"),
                        trailing_30d_sharpe=Decimal("1"))
    res = evaluate_kill_criteria(
        snapshot=snap,
        criteria=KillCriteria(auto_pause_when=[_crit("drawdown_pct", ">=", "25")]),
    )
    assert not res.fires


def test_drawdown_fires_just_above():
    snap = KillSnapshot(drawdown_pct=Decimal("25.01"),
                        daily_loss_aud=Decimal("0"),
                        trailing_30d_sharpe=Decimal("1"))
    res = evaluate_kill_criteria(
        snapshot=snap,
        criteria=KillCriteria(auto_pause_when=[_crit("drawdown_pct", ">=", "25")]),
    )
    assert res.fires


# ── daily_loss_aud boundary ─────────────────────────────────────

def test_daily_loss_fires_at_exactly_100():
    snap = KillSnapshot(drawdown_pct=Decimal("0"),
                        daily_loss_aud=Decimal("100"),
                        trailing_30d_sharpe=Decimal("1"))
    res = evaluate_kill_criteria(
        snapshot=snap,
        criteria=KillCriteria(auto_pause_when=[
            _crit("daily_loss_aud", ">=", "100"),
        ]),
    )
    assert res.fires


def test_daily_loss_does_not_fire_at_99_99():
    snap = KillSnapshot(drawdown_pct=Decimal("0"),
                        daily_loss_aud=Decimal("99.99"),
                        trailing_30d_sharpe=Decimal("1"))
    res = evaluate_kill_criteria(
        snapshot=snap,
        criteria=KillCriteria(auto_pause_when=[
            _crit("daily_loss_aud", ">=", "100"),
        ]),
    )
    assert not res.fires


# ── trailing_30d_sharpe (negative direction) ────────────────────

def test_sharpe_below_threshold_fires():
    snap = KillSnapshot(drawdown_pct=Decimal("0"),
                        daily_loss_aud=Decimal("0"),
                        trailing_30d_sharpe=Decimal("-0.5"))
    res = evaluate_kill_criteria(
        snapshot=snap,
        criteria=KillCriteria(auto_pause_when=[
            _crit("trailing_30d_sharpe", "<", "-0.5"),
        ]),
    )
    assert not res.fires   # -0.5 is not strictly < -0.5

    snap2 = KillSnapshot(drawdown_pct=Decimal("0"),
                         daily_loss_aud=Decimal("0"),
                         trailing_30d_sharpe=Decimal("-0.51"))
    res2 = evaluate_kill_criteria(
        snapshot=snap2,
        criteria=KillCriteria(auto_pause_when=[
            _crit("trailing_30d_sharpe", "<", "-0.5"),
        ]),
    )
    assert res2.fires


# ── multiple criteria — first match wins ────────────────────────

def test_first_matching_criterion_wins():
    snap = KillSnapshot(drawdown_pct=Decimal("30"),
                        daily_loss_aud=Decimal("200"),
                        trailing_30d_sharpe=Decimal("1"))
    res = evaluate_kill_criteria(
        snapshot=snap,
        criteria=KillCriteria(auto_pause_when=[
            _crit("daily_loss_aud", ">=", "100"),     # listed first
            _crit("drawdown_pct", ">=", "25"),
        ]),
    )
    assert res.fires
    assert res.matched_metric == "daily_loss_aud"


def test_no_criteria_never_fires():
    snap = KillSnapshot(drawdown_pct=Decimal("50"),
                        daily_loss_aud=Decimal("500"),
                        trailing_30d_sharpe=Decimal("-10"))
    res = evaluate_kill_criteria(snapshot=snap, criteria=KillCriteria())
    assert not res.fires
