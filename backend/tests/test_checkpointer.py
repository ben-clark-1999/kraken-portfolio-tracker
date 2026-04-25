import pytest
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from backend.agent.checkpointer import extract_messages


def test_extract_messages_filters_to_human_and_ai():
    messages = [
        HumanMessage(content="What's my portfolio worth?"),
        AIMessage(content="Your portfolio is worth $5,000."),
    ]
    result = extract_messages(messages)
    assert len(result) == 2
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "What's my portfolio worth?"
    assert result[1]["role"] == "assistant"
    assert result[1]["content"] == "Your portfolio is worth $5,000."


def test_extract_messages_skips_tool_messages():
    messages = [
        HumanMessage(content="Hi"),
        AIMessage(content="", tool_calls=[{"id": "1", "name": "get_prices", "args": {}}]),
        ToolMessage(content='{"ETH": "4000"}', tool_call_id="1"),
        AIMessage(content="ETH is $4,000."),
    ]
    result = extract_messages(messages)
    assert len(result) == 3
    assert result[0]["role"] == "user"
    assert result[1]["role"] == "assistant"
    assert result[1]["content"] == ""
    assert result[2]["role"] == "assistant"
    assert result[2]["content"] == "ETH is $4,000."


def test_extract_messages_empty_list():
    assert extract_messages([]) == []
