"""Verify the agent loop handles max-iteration overrun honestly."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend.agent.graph import _run_agent_loop


@pytest.mark.asyncio
async def test_max_iterations_injects_user_facing_message(monkeypatch):
    """When the loop hits its iteration cap, the agent must inject a final
    AIMessage explaining the situation rather than silently truncating."""

    # Fake model that always wants to call a tool — guarantees iteration cap is hit.
    fake_response = MagicMock(spec=AIMessage)
    fake_response.tool_calls = [{"name": "noop_tool", "args": {}, "id": "call_1"}]
    fake_response.content = ""

    fake_model = MagicMock()
    fake_model.ainvoke = AsyncMock(return_value=fake_response)
    fake_model.bind_tools = MagicMock(return_value=fake_model)

    monkeypatch.setattr(
        "backend.agent.graph.ChatAnthropic",
        MagicMock(return_value=fake_model),
    )

    fake_tool = MagicMock()
    fake_tool.name = "noop_tool"
    fake_tool.ainvoke = AsyncMock(return_value="ok")

    state = {
        "messages": [HumanMessage(content="loop forever")],
        "classification": None,
    }
    config = {"configurable": {"thread_id": "test-thread"}}

    result = await _run_agent_loop(state, config, [fake_tool], "system prompt")

    # The final message should be the iteration-cap notice.
    last = result["messages"][-1]
    assert isinstance(last, AIMessage)
    assert "narrow" in last.content.lower() or "smaller" in last.content.lower()


import asyncio


@pytest.mark.asyncio
async def test_invoke_tool_with_timeout_sanitizes_exception():
    """Tool exceptions must not leak into the LLM context as raw Python text."""
    from backend.agent.tools import invoke_tool_with_timeout

    fake_tool = MagicMock()
    fake_tool.name = "broken_tool"
    fake_tool.ainvoke = AsyncMock(side_effect=ValueError("internal API key abc123 leaked"))

    result = await invoke_tool_with_timeout(fake_tool, {})

    assert "abc123" not in result
    assert "ValueError" not in result
    assert "broken_tool" in result  # tool name is fine to surface
    assert "fail" in result.lower() or "error" in result.lower()
