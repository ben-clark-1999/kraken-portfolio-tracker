"""Aggregates health signals for the frontend status banner (spec §9.3)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import perf_counter

from backend.db.supabase_client import get_supabase


logger = logging.getLogger(__name__)


def build_health_payload(schema: str = "public") -> dict:
    from backend.services.trading import strategy_loop as sl

    executor = sl._current_executor
    now = datetime.now(timezone.utc)
    ws_feed: dict[str, dict] = {}
    open_orders_count = 0
    last_fill_at = None
    db_error: str | None = None

    if executor is not None:
        for pair, book in (getattr(executor, "_books", {}) or {}).items():
            age = book.age_seconds(now) if book.ts else None
            ws_feed[pair] = {
                "last_tick_at": book.ts.isoformat() if book.ts else None,
                "age_s": age,
            }

    sb = get_supabase()
    started = perf_counter()
    try:
        r = (sb.schema(schema).table("paper_orders").select("id", count="exact")
               .in_("status", ["pending", "partial"]).limit(0).execute())
        open_orders_count = r.count or 0
        last = (sb.schema(schema).table("paper_fills").select("filled_at")
                  .order("filled_at", desc=True).limit(1).execute().data)
        last_fill_at = last[0]["filled_at"] if last else None
    except Exception as exc:
        # Don't crash the health endpoint if the DB query fails — but surface
        # the error in the response so the operator can see it instead of
        # silently treating "0 open orders / no recent fills" as ground truth.
        logger.exception("health: DB query for paper_orders/paper_fills failed")
        db_error = str(exc)
    db_write_ms = int((perf_counter() - started) * 1000)

    strategies = (sb.schema(schema).table("strategies")
                    .select("id, name, status").execute().data or [])

    return {
        "ws_feed": ws_feed,
        "strategies": strategies,
        "executor": {
            "last_fill_at": last_fill_at,
            "open_orders": open_orders_count,
        },
        "db": {"write_latency_ms_p99": db_write_ms, "error": db_error},
    }
