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
    from backend.services.manual_cash_flow_scanner import ensure_cash_flows_fresh
    from backend.services.trading import metrics

    sb = get_supabase()
    strats = (sb.schema(SCHEMA).table("strategies").select("*")
                .neq("status", "archived").execute().data or [])
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)

    # Window start = earliest active strategy's created_at. Falls back to
    # 30 days ago if no strategies exist.
    window_start_dt = (
        min(datetime.fromisoformat(s["created_at"].replace("Z", "+00:00"))
            for s in strats)
        if strats
        else datetime.now(timezone.utc) - timedelta(days=30)
    )

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
            "lifetime_return_pct": str(all_time),   # paper: lifetime == all-time
            "sharpe": str(sharpe),
            "max_drawdown_pct": str(max_dd),
            "trades": trades,
            "cost_30d_aud": str(cost_30d),
            "persona_prompt_stable_since": s.get("persona_prompt_stable_since"),
        })

    # ── Manual row ──────────────────────────────────────────────────
    try:
        ensure_cash_flows_fresh(schema=SCHEMA)
        manual_row = _compute_manual_row(
            window_start_dt=window_start_dt, schema=SCHEMA,
        )
        if manual_row is not None:
            out.append(manual_row)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "Manual leaderboard row computation failed; rendering without it"
        )

    out.sort(
        key=lambda r: Decimal(r.get("return_all_time_pct") or "0"),
        reverse=True,
    )
    return out


def _compute_manual_row(*, window_start_dt, schema: str) -> dict | None:
    """Build the Manual leaderboard row from portfolio_snapshots + cash flows.

    Returns None if there's no portfolio data to summarise.
    """
    from backend.services.manual_performance import (
        CashFlowEvent, EquityPoint, compute_twr,
    )
    from backend.repositories import manual_cash_flows_repo, snapshots_repo
    from backend.services.trading import metrics
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    snaps = snapshots_repo.get_all(
        from_dt=window_start_dt.isoformat(), schema=schema,
    )
    if not snaps:
        return None

    flows = manual_cash_flows_repo.list_since(
        since=window_start_dt, schema=schema,
    )

    def _to_dt(value) -> _dt:
        if isinstance(value, str):
            return _dt.fromisoformat(value.replace("Z", "+00:00"))
        return value

    equity_points = [
        EquityPoint(
            captured_at=_to_dt(s.captured_at),
            total_value_aud=Decimal(str(s.total_value_aud)),
        )
        for s in snaps
    ]

    cash_flows = [
        CashFlowEvent(
            occurred_at=_to_dt(f["occurred_at"]),
            amount_aud=Decimal(str(f["amount_aud"])),
            kind=f["kind"],
        )
        for f in flows
    ]

    twr_pct, unit_curve = compute_twr(equity_points, cash_flows)
    sharpe = metrics.sharpe_24_7(unit_curve)
    max_dd = metrics.max_drawdown_pct(unit_curve)

    def _windowed(days: int) -> Decimal:
        cutoff = _dt.now(_tz.utc) - _td(days=days)
        window_snaps = [p for p in equity_points if p.captured_at >= cutoff]
        window_flows = [c for c in cash_flows if c.occurred_at >= cutoff]
        if len(window_snaps) < 2:
            return Decimal("0")
        twr_w, _ = compute_twr(window_snaps, window_flows)
        return twr_w

    all_snaps = snapshots_repo.get_all(schema=schema)
    all_equity = [
        EquityPoint(
            captured_at=_to_dt(s.captured_at),
            total_value_aud=Decimal(str(s.total_value_aud)),
        )
        for s in all_snaps
    ]
    all_flows_raw = manual_cash_flows_repo.list_since(
        since=_dt(1970, 1, 1, tzinfo=_tz.utc), schema=schema,
    )
    all_flows = [
        CashFlowEvent(
            occurred_at=_to_dt(f["occurred_at"]),
            amount_aud=Decimal(str(f["amount_aud"])),
            kind=f["kind"],
        )
        for f in all_flows_raw
    ]
    lifetime_pct, _ = compute_twr(all_equity, all_flows)

    current_equity = equity_points[-1].total_value_aud

    # Count trades: ledger-derived buy trades within the window.
    from backend.services import kraken_service as _ks
    try:
        trades_all = _ks.get_trade_history()
        window_start_ts = window_start_dt.timestamp()
        trade_count = sum(1 for t in trades_all if t["time"] >= window_start_ts)
    except Exception:
        trade_count = 0

    return {
        "id": "manual",
        "name": "Manual",
        "status": "active",
        "execution_mode": "manual",
        "equity_aud": str(current_equity),
        "return_7d_pct": str(_windowed(7)),
        "return_30d_pct": str(_windowed(30)),
        "return_all_time_pct": str(twr_pct),
        "lifetime_return_pct": str(lifetime_pct),
        "sharpe": str(sharpe),
        "max_drawdown_pct": str(max_dd),
        "trades": trade_count,
        "cost_30d_aud": "0",
        "persona_prompt_stable_since": None,
    }


@router.get("/_health")
def health() -> dict:
    from backend.services.trading.health import build_health_payload
    return build_health_payload(schema=SCHEMA)


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
