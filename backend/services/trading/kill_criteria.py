"""Kill-criteria evaluator.

Pre-committed disciplines that auto-pause a strategy. See spec §9.5 and §10.3.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from backend.models.trading import KillCriteria


SUPPORTED_METRICS = ("drawdown_pct", "daily_loss_aud", "trailing_30d_sharpe")


@dataclass
class KillSnapshot:
    drawdown_pct: Decimal
    daily_loss_aud: Decimal
    trailing_30d_sharpe: Decimal


@dataclass
class KillResult:
    fires: bool
    matched_metric: str | None = None
    matched_value: Decimal | None = None


def _cmp(a: Decimal, op: str, b: Decimal) -> bool:
    if op == ">":  return a > b
    if op == ">=": return a >= b
    if op == "<":  return a < b
    if op == "<=": return a <= b
    if op == "==": return a == b
    raise ValueError(f"Unsupported op: {op}")


def evaluate_kill_criteria(
    *, snapshot: KillSnapshot, criteria: KillCriteria,
) -> KillResult:
    for c in criteria.auto_pause_when:
        if c.metric not in SUPPORTED_METRICS:
            raise ValueError(f"Unsupported metric: {c.metric}")
        actual = getattr(snapshot, c.metric)
        if _cmp(actual, c.op, c.value):
            return KillResult(fires=True, matched_metric=c.metric,
                              matched_value=actual)
    return KillResult(fires=False)
