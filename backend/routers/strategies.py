"""API routes for the StrategiesPage (spec §8) and control plane."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.auth.dependencies import require_auth
from backend.db.supabase_client import get_supabase
from backend.repositories import (
    agent_decisions_repo,
    paper_equity_repo,
    paper_orders_repo,
    paper_positions_repo,
    strategies_repo,
)
from backend.services.trading import metrics


router = APIRouter(
    prefix="/api/strategies",
    tags=["strategies"],
    dependencies=[Depends(require_auth)],
)

SCHEMA = "public"


# ─────────────────────────── list / detail ──────────────────────

@router.get("/")
def list_strategies() -> list[dict]:
    sb = get_supabase()
    r = (sb.schema(SCHEMA).table("strategies")
           .select("*").order("created_at").execute())
    return r.data or []


@router.get("/_leaderboard")
def leaderboard() -> list[dict]:
    sb = get_supabase()
    strats = (sb.schema(SCHEMA).table("strategies").select("*")
                .neq("status", "archived").execute().data or [])
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    out: list[dict] = []
    for s in strats:
        sid = UUID(s["id"])
        curve_rows = paper_equity_repo.list_curve(sid, schema=SCHEMA)
        curve = [Decimal(str(r["equity_aud"])) for r in curve_rows]
        starting = Decimal(str(s.get("starting_balance_aud") or "0"))
        equity = curve[-1] if curve else starting
        sharpe = metrics.sharpe_24_7(curve)
        max_dd = metrics.max_drawdown_pct(curve)
        trades = (sb.schema(SCHEMA).table("paper_orders")
                    .select("id", count="exact")
                    .eq("strategy_id", s["id"])
                    .limit(0).execute().count or 0)
        cost_rows = (sb.schema(SCHEMA).table("agent_decisions")
                       .select("cost_aud")
                       .eq("strategy_id", s["id"])
                       .gte("created_at", thirty_days_ago.isoformat())
                       .execute().data or [])
        cost_30d = sum(
            (Decimal(str(r["cost_aud"])) for r in cost_rows),
            Decimal("0"),
        )

        def _ret_pct(window_days: int) -> Decimal:
            cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
            window = [Decimal(str(r["equity_aud"])) for r in curve_rows
                      if r["ts"] >= cutoff.isoformat()]
            if not window or window[0] == 0:
                return Decimal("0")
            return ((window[-1] / window[0]) - Decimal("1")) * Decimal("100")

        all_time = (((equity / starting) - Decimal("1")) * Decimal("100")
                    if starting > 0 else Decimal("0"))
        out.append({
            "id": s["id"],
            "name": s["name"],
            "status": s["status"],
            "execution_mode": s["execution_mode"],
            "equity_aud": str(equity),
            "return_7d_pct": str(_ret_pct(7)),
            "return_30d_pct": str(_ret_pct(30)),
            "return_all_time_pct": str(all_time),
            "sharpe": str(sharpe),
            "max_drawdown_pct": str(max_dd),
            "trades": trades,
            "cost_30d_aud": str(cost_30d),
            "persona_prompt_stable_since": s.get("persona_prompt_stable_since"),
        })
    out.sort(key=lambda r: Decimal(r["equity_aud"]), reverse=True)
    return out


@router.get("/{strategy_id}")
def get_strategy(strategy_id: UUID) -> dict:
    s = strategies_repo.get(strategy_id, schema=SCHEMA)
    if s is None:
        raise HTTPException(status_code=404, detail="Not found")
    return s.model_dump(mode="json")


@router.get("/{strategy_id}/decisions")
def get_decisions(strategy_id: UUID, n: int = Query(20, ge=1, le=200)) -> list[dict]:
    return agent_decisions_repo.list_recent(strategy_id, n=n, schema=SCHEMA)


@router.get("/{strategy_id}/equity")
def get_equity_curve(strategy_id: UUID, range: str = Query("30d")) -> dict:
    spans = {"1d": 1, "7d": 7, "30d": 30, "90d": 90, "all": 10_000}
    if range not in spans:
        raise HTTPException(status_code=400, detail="Bad range")
    since = datetime.now(timezone.utc) - timedelta(days=spans[range])
    strat_rows = paper_equity_repo.list_curve(strategy_id, since=since, schema=SCHEMA)
    btc = paper_equity_repo.list_benchmark_curve(
        "btc_hodl", since=since, schema=SCHEMA)
    basket = paper_equity_repo.list_benchmark_curve(
        "alt_basket_equal_weight", since=since, schema=SCHEMA)
    return {
        "strategy": strat_rows,
        "benchmarks": {
            "btc_hodl": btc,
            "alt_basket_equal_weight": basket,
        },
    }


@router.get("/{strategy_id}/open_orders")
def get_open_orders(strategy_id: UUID) -> list[dict]:
    rows = paper_orders_repo.list_open_orders(strategy_id, schema=SCHEMA)
    return [r.model_dump(mode="json") for r in rows]


@router.get("/{strategy_id}/positions")
def get_positions(strategy_id: UUID) -> dict:
    return paper_positions_repo.get_all(strategy_id, schema=SCHEMA)


# ─────────────────────────── control ────────────────────────────

@router.post("/{strategy_id}/pause")
def pause(strategy_id: UUID) -> dict:
    strategies_repo.update_status(strategy_id, "paused", schema=SCHEMA)
    return {"ok": True}


@router.post("/{strategy_id}/resume")
def resume(strategy_id: UUID) -> dict:
    strategies_repo.update_status(strategy_id, "active", schema=SCHEMA)
    return {"ok": True}


@router.post("/{strategy_id}/archive")
def archive(strategy_id: UUID) -> dict:
    strategies_repo.update_status(strategy_id, "archived", schema=SCHEMA)
    return {"ok": True}
