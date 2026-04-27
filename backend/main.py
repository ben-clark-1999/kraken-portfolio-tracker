import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.auth.dependencies import require_auth
from backend.error_handlers import handle_uncaught_exception
from backend.middleware.request_id import RequestIDMiddleware
from backend.scheduler import start_scheduler, stop_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── MCP tools ───────────────────────────────────────────────────
    from backend.agent.tools import MCPToolManager

    tool_manager = MCPToolManager()
    try:
        tools = await tool_manager.start()
        app.state.mcp_tool_manager = tool_manager
        logger.info("[Startup] MCP tools loaded: %d", len(tools))
    except Exception:
        logger.exception("[Startup] MCP tool loading failed — agent unavailable")
        tools = []
        app.state.mcp_tool_manager = None

    # ── Checkpointer ────────────────────────────────────────────────
    from backend.agent.checkpointer import create_checkpointer

    try:
        checkpointer = create_checkpointer()
        logger.info("[Startup] Checkpointer ready")
    except Exception:
        logger.exception("[Startup] Checkpointer setup failed — agent unavailable")
        checkpointer = None

    # ── Agent graph ─────────────────────────────────────────────────
    if tools and checkpointer:
        from backend.agent.graph import build_graph

        app.state.agent_graph = build_graph(tools, checkpointer)
        logger.info("[Startup] Agent graph compiled")
    else:
        app.state.agent_graph = None
        logger.warning("[Startup] Agent graph NOT available")

    # ── Scheduler ───────────────────────────────────────────────────
    start_scheduler()

    yield

    # ── Shutdown ────────────────────────────────────────────────────
    stop_scheduler()
    if app.state.mcp_tool_manager:
        await app.state.mcp_tool_manager.stop()


app = FastAPI(title="Kraken Portfolio Tracker", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
app.add_middleware(RequestIDMiddleware)
app.add_exception_handler(Exception, handle_uncaught_exception)

from backend.routers import agent, auth, history, portfolio, sync

# Auth router is unprotected (login itself can't require auth)
app.include_router(auth.router)

# REST-only routers protected uniformly at the router level
app.include_router(portfolio.router, dependencies=[Depends(require_auth)])
app.include_router(history.router, dependencies=[Depends(require_auth)])
app.include_router(sync.router, dependencies=[Depends(require_auth)])

# Agent router has both REST (per-route Depends) and a WebSocket
# (inline cookie check that closes with application code 4401 on auth failure)
app.include_router(agent.router)


@app.get("/api/health")
async def health() -> dict:
    """Public — used to confirm the server is up before login."""
    agent_ok = getattr(app.state, "agent_graph", None) is not None
    return {"status": "ok", "agent": agent_ok}
