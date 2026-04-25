"""LangGraph agent graph — classified multi-path with HITL on comparison path."""

import logging
from typing import Annotated, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.graph import END, StateGraph, add_messages
from langgraph.types import interrupt

from backend.agent.agent_config import (
    AGENT_MODEL,
    CATEGORY_TO_NODE,
    CLASSIFIER_CONFIDENCE_THRESHOLD,
    HITL_TOOLS_GENERAL,
    TOOL_SUBSETS,
)
from backend.agent.classifier import ClassifierOutput, classify, route_query
from backend.agent.prompts import (
    ANALYSIS_PROMPT,
    COMPARISON_PROMPT,
    GENERAL_PROMPT,
    QUICK_PROMPT,
    TAX_PROMPT,
)
from backend.agent.tools import filter_tools, invoke_tool_with_timeout

logger = logging.getLogger(__name__)


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    classification: dict | None


# ── Routing ─────────────────────────────────────────────────────────────


def route_after_classify(state: AgentState) -> str:
    """Conditional edge: pick agent node based on classifier output."""
    cls = state.get("classification")
    if cls is None:
        return "general_agent"
    return route_query(ClassifierOutput(**cls))


# ── Shared ReAct loop ───────────────────────────────────────────────────


HITL_REASONS: dict[str, str] = {
    "get_buy_and_hold_comparison": (
        "Fetches historical daily OHLC price data and compares against your "
        "actual DCA buys. Returns whether all-in on this asset would have "
        "outperformed your diversified strategy."
    ),
    "get_relative_performance": (
        "Fetches historical daily OHLC price data for all tracked assets and "
        "compares their percentage change over the requested period."
    ),
}

HITL_DURATION_ESTIMATES: dict[str, int] = {
    "get_buy_and_hold_comparison": 8000,
    "get_relative_performance": 5000,
}


async def _run_agent_loop(
    state: AgentState,
    config: RunnableConfig,
    tools: list[BaseTool],
    system_prompt: str,
    hitl_mode: str = "none",
) -> dict:
    """Shared ReAct loop for all agent nodes.

    hitl_mode:
      "none"       — never interrupt
      "all"        — interrupt before any tool call
      "selective"  — interrupt only for expensive tools (see _needs_hitl)
    """
    model = ChatAnthropic(model=AGENT_MODEL).bind_tools(tools)
    input_messages = [SystemMessage(content=system_prompt)] + list(state["messages"])

    max_iterations = 5
    for _ in range(max_iterations):
        response = await model.ainvoke(input_messages, config=config)
        input_messages.append(response)

        if not response.tool_calls:
            break

        for tc in response.tool_calls:
            tool_name = tc["name"]

            # HITL check — selective mode only triggers for genuinely
            # expensive calls (buy_and_hold always, relative_performance
            # only when timeframe >= 3M per spec)
            needs_hitl = hitl_mode == "all"
            if hitl_mode == "selective" and tool_name in HITL_TOOLS_GENERAL:
                if tool_name == "get_relative_performance":
                    tf = tc.get("args", {}).get("timeframe", "1M")
                    LONG_TIMEFRAMES = {"3M", "6M", "1Y", "ALL"}
                    needs_hitl = tf in LONG_TIMEFRAMES
                else:
                    needs_hitl = True

            if needs_hitl:
                approved = interrupt({
                    "tool": tool_name,
                    "params": tc["args"],
                    "reason": HITL_REASONS.get(tool_name, f"Execute {tool_name}"),
                    "estimated_duration_ms": HITL_DURATION_ESTIMATES.get(tool_name, 5000),
                })
                if not approved:
                    cancel = AIMessage(content="No problem — comparison cancelled.")
                    input_messages.append(cancel)
                    break

            # Execute tool
            tool = next((t for t in tools if t.name == tool_name), None)
            if tool is None:
                result = f"Error: Unknown tool {tool_name}"
            else:
                result = await invoke_tool_with_timeout(tool, tc["args"])

            input_messages.append(
                ToolMessage(content=result, tool_call_id=tc["id"])
            )
        else:
            # Inner for loop completed without break — continue outer loop
            continue
        # Break from outer loop if inner loop broke (HITL denied)
        break

    # Return only new messages (exclude system prompt and original messages)
    original_count = 1 + len(state["messages"])  # 1 for SystemMessage
    return {"messages": input_messages[original_count:]}


# ── Graph builder ───────────────────────────────────────────────────────


def build_graph(all_tools: list[BaseTool], checkpointer) -> "CompiledGraph":
    """Construct and compile the agent graph.

    Called once at startup with the loaded MCP tools and checkpointer.
    """
    # Pre-filter tool subsets
    quick_tools = filter_tools(all_tools, "quick")
    analysis_tools = filter_tools(all_tools, "analysis")
    tax_tools = filter_tools(all_tools, "tax")
    comparison_tools = filter_tools(all_tools, "comparison")

    # ── Node functions ──────────────────────────────────────────────

    async def classify_query(state: AgentState, config: RunnableConfig) -> dict:
        result = await classify(state["messages"])
        logger.info(
            "[Classifier] primary=%s confidence=%.2f secondary=%s",
            result.primary_category,
            result.confidence,
            result.secondary_categories,
        )
        return {"classification": result.model_dump()}

    async def quick_agent(state: AgentState, config: RunnableConfig) -> dict:
        return await _run_agent_loop(state, config, quick_tools, QUICK_PROMPT)

    async def analysis_agent(state: AgentState, config: RunnableConfig) -> dict:
        return await _run_agent_loop(state, config, analysis_tools, ANALYSIS_PROMPT)

    async def tax_agent(state: AgentState, config: RunnableConfig) -> dict:
        return await _run_agent_loop(state, config, tax_tools, TAX_PROMPT)

    async def comparison_agent(state: AgentState, config: RunnableConfig) -> dict:
        return await _run_agent_loop(
            state, config, comparison_tools, COMPARISON_PROMPT, hitl_mode="all"
        )

    async def general_agent(state: AgentState, config: RunnableConfig) -> dict:
        return await _run_agent_loop(
            state, config, all_tools, GENERAL_PROMPT, hitl_mode="selective"
        )

    # ── Build graph ─────────────────────────────────────────────────

    builder = StateGraph(AgentState)

    builder.add_node("classify_query", classify_query)
    builder.add_node("quick_agent", quick_agent)
    builder.add_node("analysis_agent", analysis_agent)
    builder.add_node("tax_agent", tax_agent)
    builder.add_node("comparison_agent", comparison_agent)
    builder.add_node("general_agent", general_agent)

    builder.set_entry_point("classify_query")

    builder.add_conditional_edges(
        "classify_query",
        route_after_classify,
        {
            "quick_agent": "quick_agent",
            "analysis_agent": "analysis_agent",
            "tax_agent": "tax_agent",
            "comparison_agent": "comparison_agent",
            "general_agent": "general_agent",
        },
    )

    builder.add_edge("quick_agent", END)
    builder.add_edge("analysis_agent", END)
    builder.add_edge("tax_agent", END)
    builder.add_edge("comparison_agent", END)
    builder.add_edge("general_agent", END)

    return builder.compile(checkpointer=checkpointer)
