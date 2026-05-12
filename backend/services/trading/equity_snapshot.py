"""Hourly equity snapshots per active strategy.

Spec §4.6, §8.2 leaderboard. Scheduled via the existing
backend/scheduler.py — see Task 31.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from backend.repositories import (
    paper_equity_repo, paper_positions_repo, strategies_repo,
)


logger = logging.getLogger(__name__)


@dataclass
class EquityPoint:
    equity_aud: Decimal
    cash_aud: Decimal
    position_value_aud: Decimal


def compute_equity_for_strategy(
    strategy_id: UUID | str, *, mids: dict[str, Decimal],
    schema: str = "public",
) -> EquityPoint:
    sid = UUID(str(strategy_id))
    rows = paper_positions_repo.get_all(sid, schema=schema)
    # supabase-py returns numeric columns as Python floats — coerce via str()
    # to avoid Decimal(float) binary-imprecision (e.g. Decimal(0.15) ≠ 0.15).
    cash = Decimal(str(rows.get("AUD", {}).get("qty", "0")))
    position_value = Decimal("0")
    for asset, row in rows.items():
        if asset == "AUD":
            continue
        pair = f"{asset}/AUD"
        qty = Decimal(str(row["qty"]))
        if pair not in mids:
            # Fall back to avg_cost — at least we don't crash.
            position_value += qty * Decimal(str(row.get("avg_cost_aud") or "0"))
            continue
        position_value += qty * mids[pair]
    return EquityPoint(
        equity_aud=cash + position_value,
        cash_aud=cash,
        position_value_aud=position_value,
    )


def snapshot_all_active(*, mids: dict[str, Decimal], schema: str = "public") -> None:
    ts = datetime.now(timezone.utc)
    for strat in strategies_repo.list_active(schema=schema):
        try:
            eq = compute_equity_for_strategy(strat.id, mids=mids, schema=schema)
            paper_equity_repo.insert_snapshot(
                strategy_id=strat.id, ts=ts,
                equity_aud=eq.equity_aud,
                cash_aud=eq.cash_aud,
                position_value_aud=eq.position_value_aud,
                schema=schema,
            )
        except Exception:
            logger.exception("Equity snapshot failed for %s", strat.name)
