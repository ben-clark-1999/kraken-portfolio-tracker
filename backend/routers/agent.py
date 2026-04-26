"""REST endpoints for the agent — session message rehydration."""

import jwt as pyjwt
from fastapi import APIRouter, Depends, Query, WebSocket

from backend.agent.checkpointer import extract_messages
from backend.auth.dependencies import COOKIE_NAME, require_auth
from backend.auth.jwt import decode_token

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/sessions/{session_id}/messages", dependencies=[Depends(require_auth)])
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
    # Must accept the WebSocket upgrade before closing with an application code.
    # Calling ws.close() before ws.accept() causes Uvicorn to reject the upgrade
    # with HTTP 403 — the browser sees close code 1006 (abnormal), not 4401.
    # Accepting first lets us send a proper application close frame (4401) that
    # the frontend can distinguish from a generic disconnect.
    token = ws.cookies.get(COOKIE_NAME)
    if not token:
        await ws.accept()
        await ws.close(code=4401)
        return
    try:
        decode_token(token)
    except pyjwt.PyJWTError:
        await ws.accept()
        await ws.close(code=4401)
        return

    from backend.agent.websocket_handler import agent_chat_endpoint
    from backend.main import app

    graph = app.state.agent_graph
    await agent_chat_endpoint(ws, graph, session_id)
