"""REST endpoints for the agent — session message rehydration."""

import jwt as pyjwt
from fastapi import APIRouter, Query, WebSocket

from backend.agent.checkpointer import extract_messages
from backend.auth.dependencies import COOKIE_NAME
from backend.auth.jwt import decode_token

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """Rehydrate conversation history from checkpoint.

    Called by the frontend on page reload or reconnect.
    """
    from backend.main import app

    graph = app.state.agent_graph
    config = {"configurable": {"thread_id": session_id}}
    state = await graph.aget_state(config)

    if not state.values:
        return {"session_id": session_id, "messages": []}

    messages = extract_messages(state.values.get("messages", []))
    return {"session_id": session_id, "messages": messages}


@router.websocket("/chat")
async def agent_chat(ws: WebSocket, session_id: str | None = Query(default=None)):
    """WebSocket endpoint for agent chat.

    Manually verifies the auth cookie before accepting the connection,
    since FastAPI dependency-based auth doesn't apply to WebSocket routes
    in the same way.
    """
    token = ws.cookies.get(COOKIE_NAME)
    if not token:
        await ws.close(code=4401)
        return
    try:
        decode_token(token)
    except pyjwt.PyJWTError:
        await ws.close(code=4401)
        return

    from backend.agent.websocket_handler import agent_chat_endpoint
    from backend.main import app

    graph = app.state.agent_graph
    await agent_chat_endpoint(ws, graph, session_id)
