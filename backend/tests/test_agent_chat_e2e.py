"""WebSocket protocol E2E test using a stub graph (no real LLM)."""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessageChunk, ToolMessage

from backend.main import app


class _StubGraph:
    """Yields a deterministic message sequence — exercises every branch of
    websocket_handler._stream_graph_response.

    Uses real AIMessageChunk / ToolMessage instances so that the isinstance()
    checks in _stream_graph_response fire correctly.
    """

    async def astream(self, input_data, config, stream_mode):
        # 1. Classification update
        yield ("updates", {
            "classify_query": {
                "classification": {
                    "primary_category": "quick", "confidence": 0.92,
                    "secondary_categories": [],
                },
            },
        })
        # 2. Tool call chunk (AIMessageChunk with tool_calls triggers tool_start)
        ai_tool = AIMessageChunk(
            content="",
            tool_calls=[{"name": "get_portfolio_summary", "args": {}, "id": "c1"}],
        )
        yield ("messages", (ai_tool, {}))
        # 3. Tool result (ToolMessage triggers tool_end)
        tm = ToolMessage(content='{"total_value_aud": 5000.0}', tool_call_id="c1")
        yield ("messages", (tm, {"langgraph_tool_name": "get_portfolio_summary"}))
        # 4. Final answer token
        ai_final = AIMessageChunk(content="Your portfolio is worth $5,000.")
        yield ("messages", (ai_final, {}))

    async def aget_state(self, config):
        state = MagicMock()
        state.values = {"messages": []}
        state.tasks = []
        return state


@pytest.fixture
def authed_client():
    """Override the agent graph to a stub and provide an auth cookie."""
    from backend.auth.jwt import encode_token

    app.state.agent_graph = _StubGraph()
    client = TestClient(app, raise_server_exceptions=True)
    client.cookies.set("auth_token", encode_token())
    return client


def test_websocket_emits_expected_message_sequence(authed_client):
    received: list[dict] = []
    with authed_client.websocket_connect("/api/agent/chat") as ws:
        # Wait for the session message
        first = ws.receive_json()
        assert first["type"] in ("session_started", "session_resumed")
        ws.send_json({"type": "user_message", "content": "value?"})

        # Drain until message_complete or error; skip ping noise
        for _ in range(50):
            msg = ws.receive_json()
            if msg["type"] == "ping":
                ws.send_json({"type": "pong"})
                continue
            received.append(msg)
            if msg["type"] in ("message_complete", "error"):
                break

    types = [m["type"] for m in received]
    assert "agent_thinking" in types
    assert "classifier_result" in types
    assert "tool_start" in types
    assert "tool_end" in types
    assert "token" in types
    assert types[-1] == "message_complete"


def test_websocket_rejects_unauthenticated_connection():
    client_no_auth = TestClient(app)
    # Don't set the cookie — server accepts then immediately closes with 4401
    with pytest.raises(Exception):  # WebSocket close with code 4401
        with client_no_auth.websocket_connect("/api/agent/chat") as ws:
            ws.receive_json()
