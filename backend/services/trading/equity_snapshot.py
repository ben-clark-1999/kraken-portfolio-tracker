"""Hourly equity snapshots per active strategy.

Spec §4.6, §8.2 leaderboard, §9.5 kill criteria. Scheduled via the
existing backend/scheduler.py — see Task 31.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from backend.repositories import (
    paper_equity_repo, paper_positions_repo,
    strategies_repo, system_alerts_repo,
)
from backend.services.trading.kill_criteria import (
    KillSnapshot, evaluate_kill_criteria,
)
from backend.services.trading.metrics import max_drawdown_pct, sharpe_24_7


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


def build_kill_snapshot(
    strategy_id: UUID | str, *,
    now: datetime | None = None, schema: str = "public",
) -> KillSnapshot:
    """Compute kill-criteria metrics from the rolling 30d equity history.

    Reads the curve fresh from the DB so it includes the snapshot that
    was just inserted (caller should insert first, then evaluate).
    """
    sid = UUID(str(strategy_id))
    now_ts = now or datetime.now(timezone.utc)
    since = now_ts - timedelta(days=30)

    snaps = paper_equity_repo.list_curve(sid, since=since, schema=schema)
    curve = [Decimal(str(s["equity_aud"])) for s in snaps]

    if not curve:
        return KillSnapshot(
            drawdown_pct=Decimal("0"),
            daily_loss_aud=Decimal("0"),
            trailing_30d_sharpe=Decimal("0"),
        )

    current_equity = curve[-1]
    drawdown = max_drawdown_pct(curve)
    sharpe = sharpe_24_7(curve)

    cutoff_24h = now_ts - timedelta(hours=24)
    snapshot_24h_equity: Decimal | None = None
    for s in snaps:
        ts = datetime.fromisoformat(s["ts"].replace("Z", "+00:00"))
        if ts >= cutoff_24h:
            snapshot_24h_equity = Decimal(str(s["equity_aud"]))
            break

    if snapshot_24h_equity is None:
        daily_loss = Decimal("0")
    else:
        diff = snapshot_24h_equity - current_equity
        daily_loss = diff if diff > 0 else Decimal("0")

    return KillSnapshot(
        drawdown_pct=drawdown,
        daily_loss_aud=daily_loss,
        trailing_30d_sharpe=sharpe,
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
            # Pre-committed disciplines (spec §9.5): auto-pause if a
            # kill criterion fires now that this snapshot is on record.
            ks = build_kill_snapshot(strat.id, now=ts, schema=schema)
            result = evaluate_kill_criteria(snapshot=ks, criteria=strat.kill_criteria)
            if result.fires:
                strategies_repo.update_status(strat.id, "paused", schema=schema)
                system_alerts_repo.insert(
                    level="warning",
                    code="KILL_CRITERIA_AUTO_PAUSED",
                    strategy_id=strat.id,
                    message=(
                        f"{strat.name} auto-paused: "
                        f"{result.matched_metric}={result.matched_value}"
                    ),
                    payload={
                        "metric": result.matched_metric,
                        "value": str(result.matched_value),
                    },
                    schema=schema,
                )
                logger.warning(
                    "Auto-paused %s on %s=%s",
                    strat.name, result.matched_metric, result.matched_value,
                )
        except Exception:
            logger.exception("Equity snapshot failed for %s", strat.name)
