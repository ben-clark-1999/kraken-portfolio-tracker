"""One-off: list agent conversations and optionally delete older ones.

Usage from repo root:
    backend/.venv/bin/python -m backend.scripts.cleanup_agent_sessions --preview
    backend/.venv/bin/python -m backend.scripts.cleanup_agent_sessions --keep 3 --apply

By default just previews. Pass --apply to actually delete.
"""
from __future__ import annotations

import argparse
import asyncio

import psycopg

from backend.config import settings


SQL_LIST = """
    SELECT thread_id, MAX(checkpoint_id) AS latest_checkpoint_id
    FROM checkpoints
    WHERE checkpoint_ns = ''
    GROUP BY thread_id
    ORDER BY latest_checkpoint_id DESC
"""

TABLES = ("checkpoint_writes", "checkpoint_blobs", "checkpoints")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", type=int, default=3, help="How many most-recent threads to keep.")
    parser.add_argument("--apply", action="store_true", help="Actually delete (default is preview-only).")
    args = parser.parse_args()

    if not settings.supabase_db_url:
        raise SystemExit("SUPABASE_DB_URL not set in .env")

    async with await psycopg.AsyncConnection.connect(settings.supabase_db_url, autocommit=False) as conn:
        async with conn.cursor() as cur:
            await cur.execute(SQL_LIST)
            rows = await cur.fetchall()

            total = len(rows)
            keep = rows[: args.keep]
            drop = rows[args.keep :]

            print(f"Total threads in checkpoints: {total}")
            print(f"Keeping {len(keep)} most-recent:")
            for tid, cid in keep:
                print(f"  KEEP  {tid}  (latest_checkpoint_id={cid})")
            print(f"Will drop {len(drop)} older threads.")

            if not args.apply:
                print("\n--preview mode. Re-run with --apply to actually delete.")
                return

            if not drop:
                print("Nothing to delete.")
                return

            drop_ids = [tid for tid, _ in drop]
            deleted_per_table: dict[str, int] = {}
            for table in TABLES:
                await cur.execute(
                    f"DELETE FROM {table} WHERE thread_id = ANY(%s)",
                    (drop_ids,),
                )
                deleted_per_table[table] = cur.rowcount or 0
            await conn.commit()

            print("\nDeleted rows:")
            for table, n in deleted_per_table.items():
                print(f"  {table}: {n}")
            print(f"Done — {len(drop_ids)} threads removed.")


if __name__ == "__main__":
    asyncio.run(main())
