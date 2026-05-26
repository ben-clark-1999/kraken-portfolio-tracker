"""REST endpoints for the agent — session message rehydration."""

import jwt as pyjwt
from fastapi import APIRouter, Depends, Query, Request, WebSocket

from backend.agent.checkpointer import extract_messages
from backend.auth.dependencies import COOKIE_NAME, require_auth
from backend.auth.jwt import decode_token

router = APIRouter(prefix="/api/agent", tags=["agent"])


@router.get("/sessions/{session_id}/messages", dependencies=[Depends(require_auth)])
async def get_session_messages(session_id: str, request: Request):
    """Rehydrate conversation history from checkpoint.

    Called by the frontend on page reload or reconnect.
    """
    graph = request.app.state.agent_graph
    config = {"configurable": {"thread_id": session_id}}
    state = await graph.aget_state(config)

    if not state.values:
        return {"session_id": session_id, "messages": []}

    messages = extract_messages(state.values.get("messages", []))
    return {"session_id": session_id, "messages": messages}


@router.get("/sessions", dependencies=[Depends(require_auth)])
async def list_agent_sessions(request: Request):
    """List past conversations (most recent first) for the sidebar."""
    from datetime import datetime, timezone
    from backend.agent.checkpointer import list_session_ids, extract_messages

    graph = request.app.state.agent_graph
    checkpointer = graph.checkpointer  # AsyncPostgresSaver
    pool = checkpointer.conn  # AsyncConnectionPool

    rows = await list_session_ids(pool)
    out = []
    for thread_id, _checkpoint_id in rows:
        config = {"configurable": {"thread_id": thread_id}}
        state = await graph.aget_state(config)
        if not state.values:
            continue
        msgs = extract_messages(state.values.get("messages", []))
        first_user = next((m for m in msgs if m["role"] == "user"), None)
        if not first_user:
            continue
        title = first_user["content"][:60].strip() or "Untitled conversation"
        # Derive a timestamp from state.created_at if available; else now
        last_active = getattr(state, "created_at", None)
        if last_active is None:
            last_active = datetime.now(tz=timezone.utc).isoformat()
        out.append({
            "id": thread_id,
            "title": title,
            "last_active_at": last_active,
        })
    return {"sessions": out}


@router.delete("/sessions/{session_id}", dependencies=[Depends(require_auth)])
async def delete_agent_session(session_id: str, request: Request):
    """Permanently delete a conversation from the checkpointer."""
    from backend.agent.checkpointer import delete_session

    graph = request.app.state.agent_graph
    checkpointer = graph.checkpointer
    pool = checkpointer.conn
    deleted = await delete_session(pool, session_id)
    return {"session_id": session_id, "rows_deleted": deleted}


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

    graph = ws.app.state.agent_graph
    await agent_chat_endpoint(ws, graph, session_id)
