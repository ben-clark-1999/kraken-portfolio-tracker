# ────────────────────────────────────────────────────────────────────────────
# This server is read-only. It must never expose trading, deposit, or
# withdrawal tools. The underlying Kraken API key is scoped to read-only
# permissions; trade execution is an explicit future decision that requires
# key rotation and separate safety review.
# ────────────────────────────────────────────────────────────────────────────

import asyncio
import json

from mcp.server.fastmcp import FastMCP

from datetime import timedelta

from backend.services import kraken_service, portfolio_service, snapshot_service, sync_service
from backend.services.kraken_service import ASSET_MAP
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


if __name__ == "__main__":
    mcp.run()
