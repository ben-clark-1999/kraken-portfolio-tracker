"""In-process LangChain tools for the LangGraph agent.

This file gives the AI agent its tools, running inside the main program. 
It takes the tool functions from mcp_server.py and repackages them for the agent 
— without starting a separate program. That matters because the paper-trading 
tools need to reach live data held in the main program's memory (the order books 
and the trade executor), and a separate program can't see that data — which is 
exactly why those tools failed once it went live. The real function code stays in 
mcp_server.py and keeps its MCP labels, so you could still run it as a proper MCP 
server for an outside tool one day. Here, we just grab those plain functions and 
re-wrap them for the agent
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
