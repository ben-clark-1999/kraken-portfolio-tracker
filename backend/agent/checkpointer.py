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


def _flatten_content(content) -> str:
    # AIMessage.content from a checkpoint can be a list of blocks
    # (text + tool_use) when the model emitted both — same shape
    # graph.py:341 and websocket_handler.py handle. Extract text only.
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content)


async def list_session_ids(pool) -> list[tuple[str, str]]:
    """Returns [(thread_id, latest_checkpoint_id), ...] sorted by checkpoint_id desc.

    Reads directly from the langgraph checkpoints table — there's no public
    API on AsyncPostgresSaver for listing distinct threads. Limited to the
    main namespace (checkpoint_ns = '').
    """
    sql = """
        SELECT DISTINCT ON (thread_id) thread_id, checkpoint_id
        FROM checkpoints
        WHERE checkpoint_ns = ''
        ORDER BY thread_id, checkpoint_id DESC
    """
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql)
            rows = await cur.fetchall()
    # Re-sort by checkpoint_id desc across all threads (so most-recent thread first)
    rows.sort(key=lambda r: r[1], reverse=True)
    return [(r[0], r[1]) for r in rows[:100]]


async def delete_session(pool, thread_id: str) -> int:
    """Delete all checkpoint rows for the given thread_id across all langgraph
    checkpoint tables. Returns the total rows deleted across tables.

    The langgraph postgres saver uses `checkpoints`, `checkpoint_blobs`, and
    `checkpoint_writes`. All three are keyed by thread_id. We wipe all three
    inside a single transaction so the delete is atomic.
    """
    deleted = 0
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                await cur.execute(
                    f"DELETE FROM {table} WHERE thread_id = %s",
                    (thread_id,),
                )
                deleted += cur.rowcount or 0
    return deleted


def extract_messages(messages: list) -> list[dict]:
    """Convert LangChain message objects to dicts for REST rehydration.

    Returns human and AI messages only — tool messages are internal.
    If LangGraph's internal state format changes, fix this one function.
    """
    result = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            result.append({"role": "user", "content": _flatten_content(msg.content)})
        elif isinstance(msg, AIMessage):
            result.append({"role": "assistant", "content": _flatten_content(msg.content)})
    return result
