"""LLM strategy invocation — assembles context, calls LangGraph, writes decision.

Spec §7.2 strategy-invocation mode: scoped tool surface (the five
paper-trading tools only). The actual graph call wires into the existing
LangGraph agent — we don't reinvent it here.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from time import perf_counter

from backend.models.trading import StrategyRow
from backend.services.trading.cost_model import aud_per_usd, compute_cost_aud
from backend.services.trading.decision_writer import write_agent_decision
from backend.services.trading.persona_loader import (
    load_persona, persona_hash,
)

logger = logging.getLogger(__name__)


async def _call_langgraph(
    *, system_prompt: str, user_message: str, model: str,
    tools_whitelist: list[str], strategy_id,
) -> dict:
    """Invoke the existing LangGraph agent with a scoped toolset.

    Returns a dict with keys: agent_output, tool_calls, input_tokens,
    output_tokens, model.
    """
    from backend.agent.graph import invoke_for_strategy
    return await invoke_for_strategy(
        system_prompt=system_prompt,
        user_message=user_message,
        model=model,
        tools_whitelist=tools_whitelist,
        strategy_id=str(strategy_id),
    )


def _assemble_context(strategy: StrategyRow, event, *, schema: str = "public") -> tuple[str, dict]:
    """Returns (user_message, input_snapshot)."""
    from backend.repositories import (
        agent_decisions_repo, paper_orders_repo, paper_positions_repo,
    )
    positions = paper_positions_repo.get_all(strategy.id, schema=schema)
    open_orders = paper_orders_repo.list_open_orders(strategy.id, schema=schema)
    recent = agent_decisions_repo.list_recent(strategy.id, n=5, schema=schema)
    snapshot = {
        "positions": {k: dict(v) for k, v in positions.items()},
        "open_orders": [o.model_dump(mode="json") for o in open_orders],
        "recent_decisions": [
            {"created_at": r["created_at"],
             "agent_output": r.get("agent_output"),
             "tool_calls": r.get("tool_calls", [])}
            for r in recent
        ],
        "trigger": (event.model_dump(mode="json") if hasattr(event, "model_dump")
                    else dict(event)),
    }
    user_msg = (
        f"You are running as {strategy.name} (strategy_id={strategy.id}).\n"
        f"Trigger event: {event.type}.\n"
        f"Decide what to do, calling tools as needed. "
        f"Use idempotency_key prefix `{strategy.id}:<decision_id>:<seq>`."
    )
    return user_msg, snapshot


async def invoke_llm_strategy(strategy: StrategyRow, event) -> None:
    from backend.repositories import agent_decisions_repo, strategies_repo
    from backend.services.trading import strategy_loop as sl
    schema = sl._current_schema
    started = perf_counter()
    persona = load_persona(strategy.persona_key)
    current_hash = persona_hash(strategy.persona_key)

    # Persona-prompt drift detection (spec §4.1 persona_prompt_stable_since):
    # if the persona file changed since the last invocation, reset the
    # strategy's stable-since timestamp so the leaderboard's stability
    # asterisk fires for 7d/30d returns that span the change.
    recent = agent_decisions_repo.list_recent(strategy.id, n=1, schema=schema)
    last_hash = recent[0].get("persona_prompt_hash") if recent else None
    if last_hash != current_hash:
        strategies_repo.update_persona_stable_since(
            strategy.id, datetime.now(timezone.utc), schema=schema,
        )

    user_msg, snapshot = _assemble_context(strategy, event, schema=schema)
    model = strategy.model_preference or "claude-sonnet-4-6"

    response = await _call_langgraph(
        system_prompt=persona.body, user_message=user_msg,
        model=model,
        tools_whitelist=[
            "place_paper_order", "cancel_paper_order",
            "get_my_paper_state", "get_my_recent_decisions",
            "get_market_snapshot",
        ],
        strategy_id=strategy.id,
    )

    cost = compute_cost_aud(
        model=response.get("model", model),
        input_tokens=response.get("input_tokens", 0),
        output_tokens=response.get("output_tokens", 0),
        aud_per_usd=aud_per_usd(),
    )

    write_agent_decision(
        strategy_id=strategy.id,
        execution_mode="llm_agent",
        trigger_event=(event.model_dump(mode="json") if hasattr(event, "model_dump")
                       else dict(event)),
        input_snapshot=snapshot,
        persona_prompt_hash=current_hash,
        model=response.get("model", model),
        input_tokens=response.get("input_tokens", 0),
        output_tokens=response.get("output_tokens", 0),
        cost_aud=cost,
        tool_calls=response.get("tool_calls", []),
        agent_output=response.get("agent_output"),
        latency_ms=int((perf_counter() - started) * 1000),
        error=None,
        schema=schema,
    )
