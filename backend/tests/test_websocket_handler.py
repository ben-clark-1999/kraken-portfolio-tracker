import pytest
from backend.agent.websocket_handler import (
    make_session_started,
    make_session_resumed,
    make_classifier_result,
    make_token,
    make_tool_start,
    make_tool_end,
    make_hitl_request,
    make_message_complete,
    make_error,
)


def test_session_started():
    msg = make_session_started("abc-123")
    assert msg == {"type": "session_started", "session_id": "abc-123"}


def test_session_resumed():
    msg = make_session_resumed("abc-123")
    assert msg == {"type": "session_resumed", "session_id": "abc-123"}


def test_classifier_result():
    msg = make_classifier_result("tax", 0.91)
    assert msg["type"] == "classifier_result"
    assert msg["primary_category"] == "tax"
    assert msg["confidence"] == 0.91


def test_token():
    msg = make_token("Hello")
    assert msg == {"type": "token", "content": "Hello"}


def test_tool_start():
    msg = make_tool_start("get_prices", {"assets": ["ETH"]})
    assert msg["type"] == "tool_start"
    assert msg["tool"] == "get_prices"
    assert msg["params"] == {"assets": ["ETH"]}


def test_tool_end():
    msg = make_tool_end("get_prices", 342)
    assert msg == {"type": "tool_end", "tool": "get_prices", "duration_ms": 342}


def test_hitl_request():
    msg = make_hitl_request("get_buy_and_hold_comparison", {"asset": "ETH"}, "Fetches data", 8000)
    assert msg["type"] == "hitl_request"
    assert msg["tool"] == "get_buy_and_hold_comparison"
    assert msg["estimated_duration_ms"] == 8000


def test_message_complete():
    assert make_message_complete() == {"type": "message_complete"}


def test_error():
    msg = make_error("tool_failure", "get_prices failed")
    assert msg["type"] == "error"
    assert msg["error_type"] == "tool_failure"
    assert msg["content"] == "get_prices failed"
