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
        lifetime_row = _compute_manual_lifetime_row(schema=SCHEMA)
        if lifetime_row is not None:
            out.append(lifetime_row)
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
    """Build the Manual row as a synthetic strategy that starts at the
    comparison-window launch with $0 cash and $0 positions, then mirrors
    the user's Kraken activity since then.

    Reads from the durable `manual_cash_flows` + `manual_trades` tables
    (kept fresh by manual_cash_flow_scanner) rather than calling Kraken
    at request time. That way a transient Kraken REST hiccup doesn't
    make Manual read as "$0, 0 trades" when the user actually has
    activity recorded in DB.

    Current crypto prices still come from Kraken at request time; if
    those fail we fall back to the trade's executed AUD price so equity
    is at least a sane estimate.
    """
    from backend.repositories import manual_cash_flows_repo, manual_trades_repo
    from backend.services import kraken_service as _ks
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    cash_flows = manual_cash_flows_repo.list_since(
        since=window_start_dt, schema=schema,
    )
    trades = manual_trades_repo.list_since(
        since=window_start_dt, schema=schema,
    )

    cash = Decimal("0")
    net_deposits = Decimal("0")
    for f in cash_flows:
        amt = Decimal(str(f["amount_aud"]))
        if f["kind"] == "deposit":
            cash += amt
            net_deposits += amt
        elif f["kind"] == "withdrawal":
            cash -= amt
            net_deposits -= amt

    positions: dict[str, Decimal] = {}
    avg_cost: dict[str, Decimal] = {}            # for price-fallback
    fees_30d_aud = Decimal("0")
    thirty_days_ago_dt = _dt.now(_tz.utc) - _td(days=30)
    trade_count = 0
    for t in trades:
        qty = Decimal(str(t["base_qty"]))
        aud = Decimal(str(t["aud_amount"]))
        fee = Decimal(str(t.get("fee_aud") or 0))
        asset = t["base_asset"]
        if t["side"] == "buy":
            cash -= aud
            positions[asset] = positions.get(asset, Decimal("0")) + qty
            avg_cost[asset] = (aud / qty) if qty > 0 else Decimal("0")
        elif t["side"] == "sell":
            cash += aud
            positions[asset] = positions.get(asset, Decimal("0")) - qty
        trade_count += 1
        occurred = _dt.fromisoformat(t["occurred_at"].replace("Z", "+00:00"))
        if occurred >= thirty_days_ago_dt:
            fees_30d_aud += fee

    # Current equity = synthetic cash + crypto positions at current prices.
    held = [a for a, q in positions.items() if q > 0]
    try:
        prices = _ks.get_ticker_prices(held) if held else {}
    except Exception:
        prices = {}
    pos_value = Decimal("0")
    for asset, qty in positions.items():
        if qty <= 0:
            continue
        price = prices.get(asset) or avg_cost.get(asset) or Decimal("0")
        pos_value += qty * price
    current_equity = cash + pos_value

    # Cash-on-cash return since launch. If no money has been deployed yet,
    # the row exists but returns nothing comparable — show 0%.
    if net_deposits > 0:
        return_pct = ((current_equity - net_deposits) / net_deposits) * Decimal("100")
    else:
        return_pct = Decimal("0")

    # Sharpe / max-DD need an equity curve over time. We don't synthesise
    # one yet — show 0 until enough data accumulates to make them honest.
    sharpe = Decimal("0")
    max_dd = Decimal("0")
    twr_pct = return_pct

    return {
        "id": "manual",
        "name": "Manual",
        "status": "active",
        "execution_mode": "manual",
        "equity_aud": str(current_equity),
        "return_7d_pct": str(return_pct),
        "return_30d_pct": str(return_pct),
        "return_all_time_pct": str(twr_pct),
        "sharpe": str(sharpe),
        "max_drawdown_pct": str(max_dd),
        "trades": trade_count,
        "cost_30d_aud": str(fees_30d_aud),
        "persona_prompt_stable_since": None,
    }


def _compute_manual_lifetime_row(*, schema: str) -> dict | None:
    """Build the 'Manual (all time)' row: full-history cash-on-cash on
    every dollar the user has ever put on Kraken.

    Unlike `_compute_manual_row`, which mirrors the paper-strategy frame
    (only trades since the comparison window opened), this row answers
    the simpler question: "did your existing crypto stack outperform
    holding cash, summed over your entire investing history?".

      equity   = latest portfolio_snapshots.total_value_aud
                 (full Kraken crypto value — includes staking gains)
      deposits = sum(deposits) - sum(withdrawals) across all time
      return   = (equity - deposits) / deposits

    Returns None if there's no snapshot or no deposits to compare against.
    """
    from backend.repositories import (
        manual_cash_flows_repo, manual_trades_repo, snapshots_repo,
    )
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz

    snaps = snapshots_repo.get_all(schema=schema)
    if not snaps:
        return None
    latest = max(snaps, key=lambda s: s.captured_at)
    equity = Decimal(str(latest.total_value_aud))

    epoch = _dt(1970, 1, 1, tzinfo=_tz.utc)
    flows = manual_cash_flows_repo.list_since(since=epoch, schema=schema)
    net_deposits = Decimal("0")
    for f in flows:
        amt = Decimal(str(f["amount_aud"]))
        if f["kind"] == "deposit":
            net_deposits += amt
        elif f["kind"] == "withdrawal":
            net_deposits -= amt

    if net_deposits <= 0:
        return None
    return_pct = ((equity - net_deposits) / net_deposits) * Decimal("100")

    trades = manual_trades_repo.list_since(since=epoch, schema=schema)
    trade_count = len(trades)
    thirty_days_ago_dt = _dt.now(_tz.utc) - _td(days=30)
    fees_30d_aud = Decimal("0")
    for t in trades:
        occurred = _dt.fromisoformat(t["occurred_at"].replace("Z", "+00:00"))
        if occurred >= thirty_days_ago_dt:
            fees_30d_aud += Decimal(str(t.get("fee_aud") or 0))

    return {
        "id": "manual-lifetime",
        "name": "Manual (all time)",
        "status": "active",
        "execution_mode": "manual",
        "equity_aud": str(equity),
        "return_7d_pct": str(return_pct),
        "return_30d_pct": str(return_pct),
        "return_all_time_pct": str(return_pct),
        "sharpe": "0",
        "max_drawdown_pct": "0",
        "trades": trade_count,
        "cost_30d_aud": str(fees_30d_aud),
        "persona_prompt_stable_since": None,
    }


@router.get("/_health")
def health() -> dict:
    from backend.services.trading.health import build_health_payload
    return build_health_payload(schema=SCHEMA)


@router.get("/manual-lifetime/equity")
def get_manual_lifetime_equity(range: str = Query("30d")) -> dict:
    """Equity curve for the 'Manual (all time)' virtual row.

    Reads portfolio_snapshots + manual_cash_flows and runs compute_twr
    so deposits during the window don't show up as phantom gains on the
    chart. The output shape matches the per-strategy equity endpoint so
    the frontend can reuse the same merging code.
    """
    from backend.repositories import (
        manual_cash_flows_repo, snapshots_repo,
    )
    from backend.services.manual_performance import (
        CashFlowEvent, EquityPoint, compute_twr,
    )

    spans = {"1d": 1, "7d": 7, "30d": 30, "90d": 90, "all": 10_000}
    if range not in spans:
        raise HTTPException(status_code=400, detail="Bad range")
    since = datetime.now(timezone.utc) - timedelta(days=spans[range])

    snaps = snapshots_repo.get_all(from_dt=since.isoformat(), schema=SCHEMA)
    btc = paper_equity_repo.list_benchmark_curve(
        "btc_hodl", since=since, schema=SCHEMA)
    basket = paper_equity_repo.list_benchmark_curve(
        "alt_basket_equal_weight", since=since, schema=SCHEMA)

    if not snaps:
        return {
            "strategy": [],
            "benchmarks": {"btc_hodl": btc, "alt_basket_equal_weight": basket},
        }

    flows_raw = manual_cash_flows_repo.list_since(since=since, schema=SCHEMA)

    def _to_dt(v):
        if isinstance(v, str):
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        return v

    equity_points = [
        EquityPoint(captured_at=_to_dt(s.captured_at),
                    total_value_aud=Decimal(str(s.total_value_aud)))
        for s in snaps
    ]
    cash_flows = [
        CashFlowEvent(occurred_at=_to_dt(f["occurred_at"]),
                      amount_aud=Decimal(str(f["amount_aud"])),
                      kind=f["kind"])
        for f in flows_raw
    ]

    _, unit_curve = compute_twr(equity_points, cash_flows)

    # Scale the synthetic-unit curve up to the window's starting value so
    # the chart's % normaliser produces the same number as the leaderboard
    # would for the same range.
    base = equity_points[0].total_value_aud
    strategy = [
        {"ts": ep.captured_at.isoformat(), "equity_aud": str(base * unit)}
        for ep, unit in zip(equity_points, unit_curve)
    ]
    return {
        "strategy": strategy,
        "benchmarks": {"btc_hodl": btc, "alt_basket_equal_weight": basket},
    }


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
