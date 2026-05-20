# ────────────────────────────────────────────────────────────────────────────
# The portfolio tools (top of this file) are read-only against the live Kraken
# API key, which is scoped read-only. Real trading via these tools would
# require key-rotation and separate safety review.
#
# The paper-trading tools at the bottom of this file write to the project's
# `paper_*` tables in Postgres — they never touch Kraken's live trading API.
# ────────────────────────────────────────────────────────────────────────────

import asyncio
import json

from mcp.server.fastmcp import FastMCP

from datetime import datetime, timedelta, timezone

from backend.services import kraken_service, portfolio_service, snapshot_service, sync_service
from backend.config.assets import ASSET_MAP
from backend.utils.timezone import now_aest, to_iso

mcp = FastMCP("kraken-portfolio")


@mcp.tool()
async def get_portfolio_summary() -> str:
    """Get current portfolio value, per-asset breakdown with quantities, AUD prices, values, cost basis, unrealised P&L, and allocation percentages."""
    summary = await asyncio.to_thread(portfolio_service.build_summary)
    return json.dumps(summary.model_dump(), default=str)


@mcp.tool()
async def get_balances() -> str:
    """Get current crypto quantities held on Kraken, including staked and bonded positions."""
    balances = await asyncio.to_thread(kraken_service.get_balances)
    return json.dumps({k: str(v) for k, v in balances.items()})


@mcp.tool()
async def get_prices(assets: list[str] | None = None) -> str:
    """Get live AUD prices for tracked crypto assets from Kraken.

    Args:
        assets: Asset names to query (e.g. ["ETH", "SOL"]). Defaults to all tracked assets.
    """
    if assets is None:
        assets = list(ASSET_MAP.keys())
    prices = await asyncio.to_thread(kraken_service.get_ticker_prices, assets)
    return json.dumps({k: str(v) for k, v in prices.items()})


@mcp.tool()
async def get_dca_history() -> str:
    """Get dollar-cost averaging history showing every individual purchase lot with acquisition date, quantity, cost paid, current value, and unrealised P&L."""
    def _get():
        lots = sync_service.get_all_lots()
        balances = kraken_service.get_balances()
        prices = kraken_service.get_ticker_prices(list(balances.keys()))
        return portfolio_service.get_dca_history(lots, prices)

    entries = await asyncio.to_thread(_get)
    return json.dumps([e.model_dump() for e in entries], default=str)


@mcp.tool()
async def get_snapshots(time_range: str = "7d") -> str:
    """Get historical portfolio value snapshots for charting trends over time.

    Args:
        time_range: Time range — "7d", "30d", or "all". Defaults to "7d".
    """
    from_dt = None
    if time_range != "all":
        days = 7 if time_range == "7d" else 30
        from_dt = to_iso(now_aest() - timedelta(days=days))

    snapshots = await asyncio.to_thread(
        snapshot_service.get_snapshots, from_dt=from_dt, to_dt=None
    )
    return json.dumps([s.model_dump() for s in snapshots], default=str)


@mcp.tool()
async def get_balance_change(timeframe: str) -> str:
    """Get portfolio value change over a specified timeframe.

    Compares the current live portfolio value against the nearest historical
    snapshot to the start of the requested period.

    Args:
        timeframe: Period to compare — "1W", "1M", "3M", "6M", "1Y", or "ALL".
    """
    result = await asyncio.to_thread(portfolio_service.get_balance_change, timeframe)
    return json.dumps(result.model_dump(), default=str)


@mcp.tool()
async def get_dca_analysis() -> str:
    """Analyse DCA buying cadence and cost basis across all assets.

    Returns per-asset breakdown of total invested, average cost basis, lot
    count, average days between buys, cadence deviation from weekly target,
    and an overall summary.
    """
    result = await asyncio.to_thread(portfolio_service.get_dca_analysis)
    return json.dumps(result.model_dump(), default=str)


@mcp.tool()
async def get_unrealised_cgt() -> str:
    """Compute unrealised capital gains tax position for each lot.

    Per-lot breakdown with days held, cost basis, current value, unrealised
    gain, CGT discount eligibility (ATO >12 months rule), and days until
    discount eligible. Summary includes total eligible/ineligible gains and
    count of lots within 30 days of eligibility.
    """
    result = await asyncio.to_thread(portfolio_service.get_unrealised_cgt)
    return json.dumps(result.model_dump(), default=str)


@mcp.tool()
async def get_buy_and_hold_comparison(asset: str) -> str:
    """Compare actual DCA portfolio outcome against hypothetical all-in on one asset.

    For each historical DCA buy, calculates what that AUD amount would have
    bought of the target asset at the same date using OHLC close prices.
    Compares the hypothetical total against actual portfolio value (from lots
    only, excluding staking rewards).

    Args:
        asset: Target asset for the hypothetical comparison (e.g. "ETH", "SOL").
    """
    result = await asyncio.to_thread(portfolio_service.get_buy_and_hold_comparison, asset)
    return json.dumps(result.model_dump(), default=str)


@mcp.tool()
async def get_relative_performance(timeframe: str) -> str:
    """Compare percentage change of all tracked assets over a timeframe.

    Returns per-asset performance (start/end price, % change, rank), pairwise
    ratios between all assets and their % change, best/worst performers, and
    spread. Uses OHLC close prices — end_date reflects the actual OHLC date
    used, which may be yesterday if today's candle hasn't closed.

    Args:
        timeframe: Period to compare — "1W", "1M", "3M", "6M", "1Y", or "ALL".
    """
    result = await asyncio.to_thread(portfolio_service.get_relative_performance, timeframe)
    return json.dumps(result.model_dump(), default=str)


@mcp.tool()
async def sync_trades() -> str:
    """Pull latest trades from Kraken and sync to the database. Returns the number of new trades imported."""
    def _sync():
        last_trade_id = sync_service.get_last_synced_trade_id()
        trades = kraken_service.get_trade_history(since_trade_id=last_trade_id)
        new_last_id = sync_service.upsert_lots(trades)
        sync_service.record_sync(
            last_trade_id=new_last_id or last_trade_id, status="success"
        )
        return {
            "new_trades_count": len(trades),
            "last_trade_id": new_last_id,
            "status": "success",
        }

    try:
        result = await asyncio.to_thread(_sync)
        return json.dumps(result)
    except Exception as e:
        try:
            sync_service.record_sync(
                last_trade_id=None, status="error", error_message=str(e)
            )
        except Exception:
            pass
        return json.dumps({"status": "error", "error": str(e)})


@mcp.resource("portfolio://summary")
async def portfolio_summary_resource() -> str:
    """Current portfolio summary — total value, positions, P&L, allocations."""
    summary = await asyncio.to_thread(portfolio_service.build_summary)
    return json.dumps(summary.model_dump(), default=str)


@mcp.resource("portfolio://snapshots/7d")
async def snapshots_7d_resource() -> str:
    """Portfolio value snapshots from the last 7 days."""
    from_dt = to_iso(now_aest() - timedelta(days=7))
    snapshots = await asyncio.to_thread(
        snapshot_service.get_snapshots, from_dt=from_dt, to_dt=None
    )
    return json.dumps([s.model_dump() for s in snapshots], default=str)


@mcp.resource("portfolio://snapshots/30d")
async def snapshots_30d_resource() -> str:
    """Portfolio value snapshots from the last 30 days."""
    from_dt = to_iso(now_aest() - timedelta(days=30))
    snapshots = await asyncio.to_thread(
        snapshot_service.get_snapshots, from_dt=from_dt, to_dt=None
    )
    return json.dumps([s.model_dump() for s in snapshots], default=str)


from backend.repositories import (
    up_accounts_repo,
    up_transactions_repo,
)

UP_SCHEMA = "public"


def _crypto_value() -> float:
    """Latest computed crypto portfolio value in AUD."""
    return portfolio_service.build_summary().total_value_aud


@mcp.tool()
def get_up_balance() -> str:
    """Current total cash across all UP accounts. Returns AUD figure with
    per-account breakdown."""
    accounts = up_accounts_repo.list_all(schema=UP_SCHEMA)
    if not accounts:
        return "No UP accounts found yet — sync may still be in progress."
    total = sum(a.balance_value for a in accounts)
    lines = [f"Total UP cash: ${total:,.2f} AUD"]
    for a in sorted(accounts, key=lambda x: -x.balance_value):
        lines.append(f"  - {a.display_name} ({a.account_type}): ${a.balance_value:,.2f}")
    return "\n".join(lines)


@mcp.tool()
def get_up_spending_by_category(since: str, until: str) -> str:
    """Total spend (negative-amount transactions only) per parent category in
    the given date range. ISO dates (YYYY-MM-DD or full ISO 8601)."""
    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
    until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
    breakdown = up_transactions_repo.spending_by_parent_category(
        since=since_dt, until=until_dt, schema=UP_SCHEMA,
    )
    if not breakdown:
        return f"No spending recorded between {since} and {until}."
    total = sum(breakdown.values())
    lines = [f"Total spending {since} → {until}: ${total:,.2f} AUD"]
    for cat, amt in sorted(breakdown.items(), key=lambda x: -x[1]):
        lines.append(f"  - {cat}: ${amt:,.2f}")
    return "\n".join(lines)


@mcp.tool()
def get_up_cashflow(since: str, until: str, granularity: str = "month") -> str:
    """Income vs expense per period. granularity: day | week | month."""
    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
    until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
    rows = up_transactions_repo.cashflow_by_period(
        since=since_dt, until=until_dt, granularity=granularity, schema=UP_SCHEMA,
    )
    if not rows:
        return "No cashflow data in that period."
    lines = [f"Cashflow {since} → {until} ({granularity}):"]
    for r in rows:
        lines.append(f"  {r['period']}: +${r['income']:,.2f} / -${r['expense']:,.2f}")
    return "\n".join(lines)


@mcp.tool()
def get_up_recent_transactions(limit: int = 10, since: str | None = None) -> str:
    """Most recent transactions across accounts — for grounding context.
    Not intended for transaction search."""
    since_dt = datetime.fromisoformat(since.replace("Z", "+00:00")) if since else None
    txs = up_transactions_repo.list_recent(limit=limit, since=since_dt, schema=UP_SCHEMA)
    if not txs:
        return "No transactions found."
    lines = [f"Most recent {len(txs)} transactions:"]
    for t in txs:
        lines.append(
            f"  {t.created_at[:10] if isinstance(t.created_at, str) else t.created_at.date()}  "
            f"{'−' if t.amount_value < 0 else '+'}${abs(t.amount_value):,.2f}  {t.description}"
        )
    return "\n".join(lines)


@mcp.tool()
def get_combined_net_worth() -> str:
    """Total net worth across crypto + UP cash. Returns AUD with breakdown."""
    crypto = _crypto_value()
    up_total = sum(a.balance_value for a in up_accounts_repo.list_all(schema=UP_SCHEMA))
    total = crypto + up_total
    return (
        f"Total net worth: ${total:,.2f} AUD\n"
        f"  Crypto: ${crypto:,.2f}\n"
        f"  UP cash: ${up_total:,.2f}"
    )


from backend.services import up_recurring_service as _up_recurring


@mcp.tool()
def get_recurring_charges() -> str:
    """Detected recurring charges (subscriptions). Returns each subscription's
    cadence, amount, and monthly-equivalent cost, sorted by largest first.
    Includes a total monthly subscription burden at the top."""
    charges = _up_recurring.find_recurring(schema=UP_SCHEMA)
    if not charges:
        return ("No recurring charges detected yet. A subscription needs to "
                "charge regularly with a stable amount before we can spot it "
                "(3 monthly charges, or 2 yearly).")
    total_monthly = sum(c.monthly_equivalent for c in charges)
    lines = [f"Total recurring subscriptions: ${total_monthly:,.2f}/month  ({len(charges)} active)"]
    for c in charges:
        if c.cadence == "yearly":
            extra = f"  (next: {c.next_expected_at.date()}, ~${c.monthly_equivalent:,.2f}/mo)"
            amount_str = f"${c.median_amount:,.2f}"
        else:
            extra = f"  (next: {c.next_expected_at.date()})"
            amount_str = f"${c.median_amount:,.2f}"
        lines.append(f"  - {c.name:24s} {c.cadence:12s} {amount_str}{extra}")
    return "\n".join(lines)


# ─────────────────────────── Paper-trading tools ───────────────────
# Spec §7.1. These tools read/write paper-trading state for LLM strategies
# at runtime. Each one routes through strategy_loop._current_executor and
# strategy_loop._current_schema, both of which are set by main.py at boot
# (and by tests for isolation).

from decimal import Decimal as _Decimal
from uuid import UUID as _UUID


def _current_paper_executor():
    """Returns the global PaperExecutor set by main.py on startup."""
    from backend.services.trading import strategy_loop as sl
    return sl._current_executor


def _current_paper_schema() -> str:
    from backend.services.trading import strategy_loop as sl
    return sl._current_schema


@mcp.tool()
def place_paper_order(
    strategy_id: str, pair: str, side: str, type: str, qty: str,
    idempotency_key: str, limit_price: str | None = None,
) -> dict:
    """Submit a paper order. Returns the OrderResult as a dict."""
    import asyncio as _aio
    from backend.models.trading import OrderResult
    executor = _current_paper_executor()
    if executor is None:
        return {"order_id": None, "status": "rejected",
                "reject_reason": "EXECUTOR_NOT_READY", "fills": []}
    coro = executor.submit_order(
        strategy_id=_UUID(strategy_id),
        idempotency_key=idempotency_key,
        pair=pair, side=side, type=type,
        qty=_Decimal(qty),
        limit_price=_Decimal(limit_price) if limit_price else None,
    )
    try:
        loop = _aio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        result: OrderResult = _aio.run(coro)
    else:
        # Already inside a running loop — bounce through a worker thread.
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_aio.run, coro)
            result = fut.result()
    return result.model_dump(mode="json")


@mcp.tool()
def cancel_paper_order(order_id: str) -> dict:
    import asyncio as _aio
    executor = _current_paper_executor()
    if executor is None:
        return {"ok": False, "reason": "EXECUTOR_NOT_READY"}
    coro = executor.cancel_order(order_id=_UUID(order_id))
    try:
        loop = _aio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        _aio.run(coro)
    else:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=1) as ex:
            ex.submit(_aio.run, coro).result()
    return {"ok": True}


@mcp.tool()
def get_my_paper_state(strategy_id: str) -> dict:
    from backend.repositories import paper_orders_repo, paper_positions_repo
    schema = _current_paper_schema()
    sid = _UUID(strategy_id)
    rows = paper_positions_repo.get_all(sid, schema=schema)
    cash = rows.get("AUD", {}).get("qty", "0")
    positions = {k: v for k, v in rows.items() if k != "AUD"}
    open_orders = paper_orders_repo.list_open_orders(sid, schema=schema)
    return {
        "cash_aud": str(cash),
        "positions": {k: {"qty": v.get("qty"),
                          "avg_cost_aud": v.get("avg_cost_aud")}
                      for k, v in positions.items()},
        "open_orders": [o.model_dump(mode="json") for o in open_orders],
    }


@mcp.tool()
def get_my_recent_decisions(strategy_id: str, n: int = 3) -> list[dict]:
    """Recent decisions for this strategy, with `agent_output` truncated.

    Without truncation, every new decision's context grows because the next
    invocation pulls the full agent_output text of N prior decisions back
    in. Observed 2026-05-13 → 2026-05-17 the input-token count climbed from
    ~9k to ~60k per call, blowing the credit budget. Keep only the first
    240 characters so Claude can sense recent stance without paying for
    every prior paragraph verbatim.
    """
    from backend.repositories import agent_decisions_repo
    rows = agent_decisions_repo.list_recent(
        _UUID(strategy_id), n=n, schema=_current_paper_schema(),
    )
    trimmed: list[dict] = []
    for r in rows:
        copy = dict(r)
        agent_output = copy.get("agent_output")
        if agent_output:
            text = str(agent_output)
            if len(text) > 240:
                copy["agent_output"] = text[:240] + "…[truncated]"
        trimmed.append(copy)
    return trimmed


@mcp.tool()
def get_market_snapshot(pairs: list[str] | None = None) -> dict:
    """Returns top-of-book per pair from the live LocalOrderBooks.

    Returns BOOK_UNAVAILABLE when the book is missing/empty or the WS
    connection itself is stale (no Kraken message in ~10s). Per-pair
    book.ts is NOT used for staleness because Kraken's book channel only
    diffs on change — a quiet pair has an old book.ts even while the
    WS connection is perfectly healthy and the book data is current.
    """
    from datetime import datetime, timezone
    executor = _current_paper_executor()
    out: dict[str, dict] = {}
    pairs = pairs or list((executor._books if executor else {}).keys())
    now = datetime.now(timezone.utc)
    for p in pairs:
        reason = (executor._book_unavailable_reason(p, now)
                  if executor is not None else "no_executor")
        if reason is not None:
            out[p] = {"error": "BOOK_UNAVAILABLE", "reason": reason}
            continue
        book = executor._books[p]
        out[p] = {
            "top_ask": {"price": str(book.top_ask().price),
                        "qty": str(book.top_ask().qty)},
            "top_bid": {"price": str(book.top_bid().price),
                        "qty": str(book.top_bid().qty)},
            "mid": str(book.mid()),
            "ts": book.ts.isoformat() if book.ts else None,
        }
    return out


if __name__ == "__main__":
    mcp.run()
