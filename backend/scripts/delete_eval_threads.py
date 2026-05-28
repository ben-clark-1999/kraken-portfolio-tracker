"""Delete checkpointer threads whose first user message exactly matches a query
from backend/evals/golden_set.yaml.

These threads were planted by `pytest -m eval` runs back when the eval test
shared the production Postgres checkpointer. They show up in the chat sidebar
as if they were real conversations, even though no human ever typed them.

Usage from repo root:
    backend/.venv/bin/python -m backend.scripts.delete_eval_threads          # preview
    backend/.venv/bin/python -m backend.scripts.delete_eval_threads --apply  # actually delete

The companion fix (backend/tests/test_evals.py using MemorySaver) prevents
future eval runs from creating any more of these.
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import yaml
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from backend.agent.checkpointer import _flatten_content, delete_session, list_session_ids
from backend.config import settings


GOLDEN_SET_PATH = Path(__file__).resolve().parents[1] / "evals" / "golden_set.yaml"


def load_golden_queries() -> set[str]:
    """Return the set of query strings from golden_set.yaml."""
    with open(GOLDEN_SET_PATH) as f:
        raw = yaml.safe_load(f)
    return {entry["query"].strip() for entry in raw if "query" in entry}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually delete (default is preview-only).",
    )
    args = parser.parse_args()

    if not settings.supabase_db_url:
        raise SystemExit("SUPABASE_DB_URL not set in .env")

    golden_queries = load_golden_queries()
    print(f"Loaded {len(golden_queries)} unique queries from golden_set.yaml")

    pool = AsyncConnectionPool(
        conninfo=settings.supabase_db_url,
        min_size=1,
        max_size=3,
        kwargs={"autocommit": True, "prepare_threshold": 0},
        open=False,
    )
    await pool.open()
    try:
        checkpointer = AsyncPostgresSaver(conn=pool)
        # No setup() needed — schema already exists from the live app.

        thread_rows = await list_session_ids(pool)
        print(f"Found {len(thread_rows)} threads in checkpoints table.")

        eval_threads: list[tuple[str, str]] = []  # (thread_id, matched_query)
        kept_threads: list[tuple[str, str]] = []  # (thread_id, first_user_msg)

        for thread_id, _checkpoint_id in thread_rows:
            config = {"configurable": {"thread_id": thread_id}}
            tup = await checkpointer.aget_tuple(config)
            if tup is None:
                continue
            msgs = tup.checkpoint.get("channel_values", {}).get("messages", [])
            first_user = next((m for m in msgs if isinstance(m, HumanMessage)), None)
            if first_user is None:
                continue
            content = _flatten_content(first_user.content).strip()
            if content in golden_queries:
                eval_threads.append((thread_id, content))
            else:
                kept_threads.append((thread_id, content[:60]))

        print()
        print(f"Will DELETE {len(eval_threads)} eval-planted threads:")
        for tid, q in eval_threads[:10]:
            print(f"  DROP  {tid}  {q!r}")
        if len(eval_threads) > 10:
            print(f"  …and {len(eval_threads) - 10} more")
        print()
        print(f"Will KEEP {len(kept_threads)} threads (no golden_set match):")
        for tid, q in kept_threads[:20]:
            print(f"  KEEP  {tid}  first msg: {q!r}")
        if len(kept_threads) > 20:
            print(f"  …and {len(kept_threads) - 20} more")

        if not args.apply:
            print("\n--preview mode. Re-run with --apply to actually delete.")
            return

        if not eval_threads:
            print("Nothing to delete.")
            return

        total = 0
        for tid, _ in eval_threads:
            total += await delete_session(pool, tid)
        print(f"\nDeleted {len(eval_threads)} threads ({total} rows across checkpoint tables).")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
