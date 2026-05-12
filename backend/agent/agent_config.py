"""Centralised configuration for the LangGraph agent.

All model choices, thresholds, timeouts, and tool subsets live here.
Swap models by changing constants — no graph rewiring needed.
"""

# ── Models ──────────────────────────────────────────────────────────────
CLASSIFIER_MODEL = "claude-haiku-4-5-20251001"
AGENT_MODEL = "claude-sonnet-4-5"

# ── Classifier routing ──────────────────────────────────────────────────
CLASSIFIER_CONFIDENCE_THRESHOLD = 0.8

# ── Tool subsets per path ───────────────────────────────────────────────
TOOL_SUBSETS: dict[str, list[str] | None] = {
    "quick": [
        "get_portfolio_summary",
        "get_balances",
        "get_prices",
        "get_dca_history",
        "get_dca_analysis",
    ],
    "analysis": [
        "get_balance_change",
        "get_relative_performance",
        "get_dca_analysis",
        "get_snapshots",
    ],
    "tax": [
        "get_unrealised_cgt",
        "get_dca_analysis",
        "get_balance_change",
    ],
    "comparison": [
        "get_buy_and_hold_comparison",
        "get_relative_performance",
    ],
    "cash": [
        "get_up_balance",
        "get_up_spending_by_category",
        "get_up_cashflow",
        "get_up_recent_transactions",
        "get_combined_net_worth",
        "get_recurring_charges",
    ],
    "general": None,  # All tools
}

# ── HITL configuration ──────────────────────────────────────────────────
# Tools requiring HITL approval on the general path
HITL_TOOLS_GENERAL = {"get_buy_and_hold_comparison", "get_relative_performance"}

# ── Timeouts ────────────────────────────────────────────────────────────
TOOL_TIMEOUT_SECONDS = 30
MCP_RESPONSIVENESS_TIMEOUT = 5

# ── WebSocket ───────────────────────────────────────────────────────────
WS_HEARTBEAT_INTERVAL = 30   # seconds
WS_HEARTBEAT_TIMEOUT = 90    # seconds without pong → close

# ── Category → node name mapping ───────────────────────────────────────
CATEGORY_TO_NODE = {
    "quick": "quick_agent",
    "analysis": "analysis_agent",
    "tax": "tax_agent",
    "comparison": "comparison_agent",
    "cash": "cash_agent",
    "open": "general_agent",
}
