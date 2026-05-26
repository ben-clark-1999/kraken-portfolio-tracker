import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.auth.dependencies import require_auth
from backend.config import settings
from backend.error_handlers import handle_uncaught_exception
from backend.middleware.request_id import RequestIDMiddleware
from backend.scheduler import start_scheduler, stop_scheduler

# pydantic-settings loads ANTHROPIC_API_KEY from .env into `settings` but does
# not propagate it to os.environ. ChatAnthropic() reads from os.environ, so
# without this bridge every LLM strategy fire raised an auth TypeError and
# auto-paused itself. Mirrors backend/tests/conftest.py.
if settings.anthropic_api_key and not os.environ.get("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

logger = logging.getLogger(__name__)


def _is_test_context() -> bool:
    """True when running under pytest — skip the heavy trading-sandbox boot."""
    return bool(os.environ.get("PYTEST_CURRENT_TEST"))


async def _boot_trading_sandbox(app: FastAPI, tools) -> None:
    """Seed strategies, validate the universe, then attach the price feed,
    strategy loops, and scheduled jobs. Each step is defensive so a single
    failure doesn't take down the rest of the API surface (spec §11)."""
    from decimal import Decimal

    from backend.agent.graph import set_strategy_tools
    from backend.repositories import strategies_repo, system_alerts_repo
    from backend.scheduler import register_all_strategy_triggers, scheduler
    from backend.scripts.seed_strategies import seed_all
    from backend.services.trading.equity_snapshot import snapshot_all_active
    from backend.services.trading.event_bus import get_default_bus
    from backend.services.trading.executor import PaperExecutor
    from backend.services.trading.min_order import filter_allowed_pairs_by_min_order
    from backend.services.trading.price_feed import PriceFeed
    from backend.services.trading.strategy_loop import set_executor, strategy_loop

    set_strategy_tools(tools)

    try:
        seed_all()
        logger.info("[Startup] Strategies seeded")
    except Exception:
        logger.exception("[Startup] Strategy seed failed")

    pairs = ["ETH/AUD", "LINK/AUD", "ADA/AUD", "SOL/AUD"]
    try:
        kept, dropped = filter_allowed_pairs_by_min_order(
            pairs=pairs, max_position_aud=Decimal("300"),
        )
        if dropped:
            for p in dropped:
                system_alerts_repo.insert(
                    level="warning", code="PAIR_DROPPED_MIN_ORDER",
                    strategy_id=None,
                    message=f"Pair {p} dropped from universe (min-order check)",
                    payload={"pair": p},
                )
        pairs = kept or pairs
    except Exception:
        logger.exception("[Startup] Min-order validation failed")

    try:
        bus = get_default_bus()
        executor = PaperExecutor()
        set_executor(executor)
        feed = PriceFeed(pairs=pairs, bus=bus, executor=executor)

        feed_task = asyncio.create_task(feed.run(), name="price_feed")
        loop_tasks = [
            asyncio.create_task(
                strategy_loop(strat, bus=bus),
                name=f"strategy_loop:{strat.name}",
            )
            for strat in strategies_repo.list_active()
        ]

        if not scheduler.running:
            start_scheduler()
        register_all_strategy_triggers()

        def _equity_job() -> None:
            mids = {
                p: b.mid()
                for p, b in (executor._books or {}).items()
                if b.ts is not None and b.asks and b.bids
            }
            try:
                snapshot_all_active(mids=mids)
            except Exception:
                logger.exception("[Equity job] snapshot failed")

        scheduler.add_job(
            _equity_job, "interval", hours=1,
            id="paper_equity_snapshot", replace_existing=True,
        )

        app.state.trading_executor = executor
        app.state.trading_feed_task = feed_task
        app.state.trading_loop_tasks = loop_tasks
        logger.info(
            "[Startup] Trading sandbox booted: %d strategy loops, %d pairs",
            len(loop_tasks), len(pairs),
        )
    except Exception as exc:
        logger.exception("[Startup] Trading sandbox boot failed")
        # Surface the failure as a system_alert so the operator sees it on
        # the dashboard rather than only in Railway logs. Best-effort — if
        # the alert insert itself fails, the logger.exception above is the
        # remaining record.
        try:
            from backend.repositories import system_alerts_repo as alerts
            alerts.insert(
                level="error", code="SANDBOX_BOOT_FAILED", strategy_id=None,
                message=f"Trading sandbox boot failed: {exc!r}",
                payload={"exception": str(exc)},
            )
        except Exception:
            logger.exception("Failed to insert SANDBOX_BOOT_FAILED alert")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Agent tools (in-process — no subprocess) ─────────────────────
    # The MCP-stdio subprocess couldn't see the parent's LocalOrderBook
    # instances or PaperExecutor singleton, so paper-trading tools always
    # returned BOOK_UNAVAILABLE / EXECUTOR_NOT_READY. Loading the same
    # functions in-process fixes that — see backend/agent/local_tools.py.
    # MCPToolManager and backend/mcp_server.py are still on disk in case
    # we want to expose an external MCP server later, but nothing uses
    # them at runtime now.
    from backend.agent.local_tools import load_local_tools

    app.state.mcp_tool_manager = None
    try:
        tools = load_local_tools()
        logger.info("[Startup] Agent tools loaded: %d", len(tools))
    except Exception:
        logger.exception("[Startup] Agent tool loading failed — agent unavailable")
        tools = []

    # ── Checkpointer ────────────────────────────────────────────────
    from backend.agent.checkpointer import create_checkpointer

    try:
        checkpointer = await create_checkpointer()
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

    # ── Trading sandbox (skipped under pytest) ──────────────────────
    app.state.trading_executor = None
    app.state.trading_feed_task = None
    app.state.trading_loop_tasks = []
    if _is_test_context():
        logger.info("[Startup] PYTEST detected — skipping trading sandbox boot")
    else:
        await _boot_trading_sandbox(app, tools)

    yield

    # ── Shutdown ────────────────────────────────────────────────────
    tasks_to_drain: list[asyncio.Task] = list(
        getattr(app.state, "trading_loop_tasks", []) or []
    )
    feed_task = getattr(app.state, "trading_feed_task", None)
    if feed_task is not None:
        tasks_to_drain.append(feed_task)

    for t in tasks_to_drain:
        t.cancel()

    # Give cancelled tasks a few seconds to clean up in-flight work (e.g. an
    # order mid-submission) rather than letting Railway kill the container
    # with half-written state. Bounded so redeploys don't hang.
    if tasks_to_drain:
        try:
            await asyncio.wait_for(
                asyncio.gather(*tasks_to_drain, return_exceptions=True),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[Shutdown] %d task(s) did not finish within 5s; container "
                "kill imminent",
                len(tasks_to_drain),
            )

    stop_scheduler()


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

from backend.routers import agent, auth, combined, history, portfolio, strategies, sync, up

# Auth router is unprotected (login itself can't require auth)
app.include_router(auth.router)

# REST-only routers protected uniformly at the router level
app.include_router(portfolio.router, dependencies=[Depends(require_auth)])
app.include_router(history.router, dependencies=[Depends(require_auth)])
app.include_router(sync.router, dependencies=[Depends(require_auth)])

app.include_router(up.router)
app.include_router(combined.router)
app.include_router(strategies.router)

# Agent router has both REST (per-route Depends) and a WebSocket
# (inline cookie check that closes with application code 4401 on auth failure)
app.include_router(agent.router)


@app.get("/api/health")
async def health() -> dict:
    """Public — used to confirm the server is up before login."""
    agent_ok = getattr(app.state, "agent_graph", None) is not None
    return {"status": "ok", "agent": agent_ok}
