"""PostgresSaver checkpointer — setup, connection pool, message extraction."""

import logging

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool

from backend.config import settings

logger = logging.getLogger(__name__)


def create_checkpointer() -> PostgresSaver:
    """Create a PostgresSaver backed by a psycopg connection pool.

    Uses the direct Supabase Postgres URL (not the pooler) to avoid
    transaction-mode pooling issues with prepared statements.
    Pool max_size=5 — Supabase free tier has 60 connections; the rest
    of the app uses PostgREST which doesn't consume connection slots.
    """
    if not settings.supabase_db_url:
        raise RuntimeError(
            "SUPABASE_DB_URL not set. Add the direct Postgres connection string "
            "(db.PROJECT_ID.supabase.co:5432) to .env."
        )

    pool = ConnectionPool(
        conninfo=settings.supabase_db_url,
        max_size=5,
        kwargs={"autocommit": True, "prepare_threshold": 0},
    )
    checkpointer = PostgresSaver(conn=pool)
    checkpointer.setup()
    logger.info("[Checkpointer] PostgresSaver initialised with pool (max_size=5)")
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
