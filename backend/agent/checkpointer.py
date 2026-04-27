"""AsyncPostgresSaver checkpointer — setup, connection pool, message extraction."""

import logging

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from backend.config import settings

logger = logging.getLogger(__name__)


async def create_checkpointer() -> AsyncPostgresSaver:
    """Create an AsyncPostgresSaver backed by an async psycopg connection pool.

    Uses the direct Supabase Postgres URL (not the pooler) to avoid
    transaction-mode pooling issues with prepared statements.
    Pool max_size=5 — Supabase free tier has 60 connections; the rest
    of the app uses PostgREST which doesn't consume connection slots.

    Must be awaited — the pool opens async connections and setup() is a
    coroutine (AsyncPostgresSaver requires async I/O paths throughout).
    """
    if not settings.supabase_db_url:
        raise RuntimeError(
            "SUPABASE_DB_URL not set. Add the direct Postgres connection string "
            "(db.PROJECT_ID.supabase.co:5432) to .env."
        )

    pool = AsyncConnectionPool(
        conninfo=settings.supabase_db_url,
        min_size=1,
        max_size=5,
        kwargs={"autocommit": True, "prepare_threshold": 0},
        open=False,
    )
    await pool.open()
    checkpointer = AsyncPostgresSaver(conn=pool)
    await checkpointer.setup()
    logger.info("[Checkpointer] AsyncPostgresSaver initialised with pool (max_size=5)")
    return checkpointer


def extract_messages(messages: list) -> list[dict]:
    """Convert LangChain message objects to dicts for REST rehydration.

    Returns human and AI messages only — tool messages are internal.
    If LangGraph's internal state format changes, fix this one function.
    """
    result = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            result.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            result.append({"role": "assistant", "content": msg.content})
    return result
