"""In-process LangChain tools for the LangGraph agent.

Wraps the FastMCP-decorated functions in `backend.mcp_server` as LangChain
BaseTool instances WITHOUT spawning a subprocess. Required so paper-trading
tools can reach parent-process state (the LocalOrderBook instances kept by
PriceFeed, and the PaperExecutor singleton on `strategy_loop._current_executor`)
— a stdio MCP subprocess can't see those globals, which is what produced
`BOOK_UNAVAILABLE` / `EXECUTOR_NOT_READY` after deploy.

The implementations themselves stay put in `backend/mcp_server.py`
(decorated with `@mcp.tool()` so the MCP server is still externally
runnable if ever needed). Here we just import the bare callables and wrap
them as LangChain tools.
"""
from __future__ import annotations

from inspect import iscoroutinefunction
from typing import Any, Callable

from langchain_core.tools import BaseTool, StructuredTool


def _wrap_function(func: Callable[..., Any]) -> BaseTool:
    """Wrap a Python function as a LangChain StructuredTool.

    Schema is inferred from the function signature; the description comes
    from the docstring (falling back to the function name).
    """
    name = func.__name__
    description = (func.__doc__ or name).strip()
    if iscoroutinefunction(func):
        return StructuredTool.from_function(
            coroutine=func, name=name, description=description,
        )
    return StructuredTool.from_function(
        func=func, name=name, description=description,
    )


def load_local_tools() -> list[BaseTool]:
    """Return every MCP-decorated tool as an in-process LangChain tool.

    Order mirrors `backend/mcp_server.py` for ease of audit.
    """
    from backend import mcp_server as m

    funcs: list[Callable[..., Any]] = [
        # ── Crypto / portfolio ───────────────────────────────────────
        m.get_portfolio_summary,
        m.get_balances,
        m.get_prices,
        m.get_dca_history,
        m.get_snapshots,
        m.get_balance_change,
        m.get_dca_analysis,
        m.get_unrealised_cgt,
        m.get_buy_and_hold_comparison,
        m.get_relative_performance,
        m.sync_trades,
        # ── UP Bank ──────────────────────────────────────────────────
        m.get_up_balance,
        m.get_up_spending_by_category,
        m.get_up_cashflow,
        m.get_up_recent_transactions,
        m.get_combined_net_worth,
        m.get_recurring_charges,
        # ── Paper trading (the ones that needed parent-process state) ─
        m.place_paper_order,
        m.cancel_paper_order,
        m.get_my_paper_state,
        m.get_my_recent_decisions,
        m.get_market_snapshot,
    ]
    return [_wrap_function(f) for f in funcs]
