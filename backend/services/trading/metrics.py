"""Strategy performance metrics. Spec §8.2 + §9.5.

Annualisation uses √365 (24/7 markets). Returns are computed as ln-returns
on the equity curve.
"""
from __future__ import annotations

import math
from decimal import Decimal
from statistics import mean, pstdev


def compute_returns(curve: list[Decimal]) -> list[Decimal]:
    if len(curve) < 2:
        return []
    out: list[Decimal] = []
    for i in range(1, len(curve)):
        if curve[i - 1] <= 0:
            continue
        ratio = float(curve[i]) / float(curve[i - 1])
        if ratio <= 0:
            continue
        out.append(Decimal(str(math.log(ratio))))
    return out


def _annualise(daily_value: float) -> Decimal:
    return Decimal(str(daily_value * math.sqrt(365)))


def sharpe_24_7(curve: list[Decimal]) -> Decimal:
    rs = [float(r) for r in compute_returns(curve)]
    if len(rs) < 2:
        return Decimal("0")
    mu = mean(rs)
    sigma = pstdev(rs)
    if sigma == 0:
        return Decimal("0")
    return _annualise(mu / sigma)


def sortino_24_7(curve: list[Decimal]) -> Decimal:
    rs = [float(r) for r in compute_returns(curve)]
    if len(rs) < 2:
        return Decimal("0")
    mu = mean(rs)
    downside = [r for r in rs if r < 0]
    if not downside:
        return Decimal("999")    # convention: no downside → huge Sortino
    dn_sigma = pstdev(downside)
    if dn_sigma == 0:
        return Decimal("0")
    return _annualise(mu / dn_sigma)


def max_drawdown_pct(curve: list[Decimal]) -> Decimal:
    if not curve:
        return Decimal("0")
    peak = curve[0]
    worst = Decimal("0")
    for v in curve:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * Decimal("100")
            if dd > worst:
                worst = dd
    return worst


def calmar(*, annualised_return_pct: Decimal, max_dd_pct: Decimal) -> Decimal:
    if max_dd_pct == 0:
        return Decimal("0")
    return (annualised_return_pct / max_dd_pct).quantize(Decimal("0.0001"))


def win_rate(returns: list[Decimal]) -> Decimal:
    if not returns:
        return Decimal("0")
    wins = sum(1 for r in returns if r > 0)
    return Decimal(wins) / Decimal(len(returns))


def payoff_ratio(returns: list[Decimal]) -> Decimal:
    wins = [r for r in returns if r > 0]
    losses = [-r for r in returns if r < 0]
    if not wins or not losses:
        return Decimal("0")
    avg_win = sum(wins) / Decimal(len(wins))
    avg_loss = sum(losses) / Decimal(len(losses))
    if avg_loss == 0:
        return Decimal("0")
    return (avg_win / avg_loss).quantize(Decimal("0.0001"))
