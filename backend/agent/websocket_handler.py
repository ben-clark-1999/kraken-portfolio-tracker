"""WebSocket endpoint for the agent — streaming, HITL, heartbeat."""

import asyncio
import logging
import time
import uuid

from fastapi import WebSocket, WebSocketDisconnect
from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage
from langgraph.types import Command

from backend.agent.agent_config import WS_HEARTBEAT_INTERVAL, WS_HEARTBEAT_TIMEOUT

logger = logging.getLogger(__name__)


# ── Message factories ───────────────────────────────────────────────────


def make_session_started(session_id: str) -> dict:
    return {"type": "session_started", "session_id": session_id}


def make_session_resumed(session_id: str) -> dict:
    return {"type": "session_resumed", "session_id": session_id}


def make_classifier_result(primary_category: str, confidence: float) -> dict:
    return {
        "type": "classifier_result",
        "primary_category": primary_category,
        "confidence": confidence,
    }


def make_token(content: str) -> dict:
    return {"type": "token", "content": content}


def make_tool_start(tool: str, params: dict) -> dict:
    return {"type": "tool_start", "tool": tool, "params": params}


def make_tool_end(tool: str, duration_ms: int) -> dict:
    return {"type": "tool_end", "tool": tool, "duration_ms": duration_ms}


def make_hitl_request(
    tool: str, params: dict, reason: str, estimated_duration_ms: int,
) -> dict:
    return {
        "type": "hitl_request",
        "tool": tool,
        "params": params,
        "reason": reason,
        "estimated_duration_ms": estimated_duration_ms,
    }


def make_message_complete() -> dict:
    return {"type": "message_complete"}


def make_error(error_type: str, content: str) -> dict:
    return {"type": "error", "error_type": error_type, "content": content}


def make_agent_thinking() -> dict:
    return {"type": "agent_thinking"}


# ── Stream processing ──────────────────────────────────────────────────


async def _stream_graph_response(ws: WebSocket, graph, session_id: str, input_data) -> None:
    """Run the graph and stream events to the WebSocket client."""
    config = {"configurable": {"thread_id": session_id}}
    tool_start_times: dict[str, float] = {}

    try:
        async for mode, data in graph.astream(
            input_data, config, stream_mode=["messages", "updates"]
        ):
            if mode == "updates":
                for node_name, update in data.items():
                    if node_name == "classify_query" and update.get("classification"):
                        cls = update["classification"]
                        await ws.send_json(
                            make_classifier_result(
                                cls["primary_category"], cls["confidence"]
                            )
                        )

            elif mode == "messages":
                chunk, metadata = data

                if isinstance(chunk, AIMessageChunk):
                    if chunk.content:
                        await ws.send_json(make_token(chunk.content))
                    if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                        for tc in chunk.tool_calls:
                            tool_start_times[tc["name"]] = time.time()
                            await ws.send_json(
                                make_tool_start(tc["name"], tc.get("args", {}))
                            )

                elif isinstance(chunk, ToolMessage):
                    tool_name = metadata.get("langgraph_tool_name", "unknown")
                    start = tool_start_times.pop(tool_name, time.time())
                    duration_ms = int((time.time() - start) * 1000)
                    await ws.send_json(make_tool_end(tool_name, duration_ms))

    except Exception as e:
        logger.exception("[WS] Error during graph streaming")
        await ws.send_json(make_error("model", str(e)))
        return

    # Check for HITL interrupt
    state = await graph.aget_state(config)
    if state.tasks and any(
        hasattr(t, "interrupts") and t.interrupts for t in state.tasks
    ):
        interrupt_info = state.tasks[0].interrupts[0].value
        await ws.send_json(
            make_hitl_request(
                tool=interrupt_info["tool"],
                params=interrupt_info["params"],
                reason=interrupt_info["reason"],
                estimated_duration_ms=interrupt_info["estimated_duration_ms"],
            )
        )
        return  # Wait for hitl_response — don't send message_complete yet

    await ws.send_json(make_message_complete())


# ── WebSocket endpoint ──────────────────────────────────────────────────


async def agent_chat_endpoint(ws: WebSocket, graph, session_id: str | None = None):
    """Main WebSocket handler — called from the FastAPI route."""
    await ws.accept()

    # Session management
    if session_id:
        # Attempt to load existing session
        config = {"configurable": {"thread_id": session_id}}
        state = await graph.aget_state(config)
        if state.values:
            await ws.send_json(make_session_resumed(session_id))
        else:
            session_id = str(uuid.uuid4())
            await ws.send_json(make_session_started(session_id))
    else:
        session_id = str(uuid.uuid4())
        await ws.send_json(make_session_started(session_id))

    last_pong = time.time()

    async def heartbeat():
        nonlocal last_pong
        while True:
            await asyncio.sleep(WS_HEARTBEAT_INTERVAL)
            try:
                await ws.send_json({"type": "ping"})
            except Exception:
                break
            if time.time() - last_pong > WS_HEARTBEAT_TIMEOUT:
                logger.warning("[WS] Client timeout — closing connection")
                await ws.close()
                break

    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "pong":
                last_pong = time.time()

            elif msg_type == "ping":
                await ws.send_json({"type": "pong"})

            elif msg_type == "user_message":
                await ws.send_json(make_agent_thinking())
                input_data = {"messages": [HumanMessage(content=data["content"])]}
                await _stream_graph_response(ws, graph, session_id, input_data)

            elif msg_type == "hitl_response":
                approved = data.get("approved", False)
                resume_input = Command(resume=approved)
                if approved:
                    await ws.send_json(make_agent_thinking())
                await _stream_graph_response(ws, graph, session_id, resume_input)

    except WebSocketDisconnect:
        logger.info("[WS] Client disconnected — session %s", session_id)
    except Exception:
        logger.exception("[WS] Unexpected error")
    finally:
        heartbeat_task.cancel()
