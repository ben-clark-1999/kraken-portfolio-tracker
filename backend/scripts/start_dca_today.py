"""Start the DCA-Baseline experiment *today* (one-off operational script).

Does two things, both safe to re-run:

1. Re-points the live DCA-Baseline cadence to Tuesdays 09:00 Australia/Sydney
   (deterministic_config.cadence_cron + the cron trigger in trigger_config).
   seed_strategies.seed_all() is idempotent and never updates an existing row,
   so the day-of-week change has to be applied to the live row here. The
   recurring schedule only re-registers on the next backend boot/redeploy —
   APScheduler reads trigger_config at startup — so the new Tuesday cadence
   takes effect on the next deploy, not in the currently-running process.

2. Fires this week's DCA slice right now by running the same deterministic
   path the scheduler would (warm the L2 books over the Kraken WS feed, then
   call invoke_deterministic_strategy once). This is GUARDED: if a DCA-Baseline
   decision already exists for today (Australia/Sydney), the fire is skipped so
   re-running can't double-spend a slice.

Run against whichever DB/keys backend.config.settings points at:
    backend/.venv/bin/python -m backend.scripts.start_dca_today
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("start_dca_today")

SYDNEY = ZoneInfo("Australia/Sydney")
TUESDAY_CRON = "0 9 * * tue"
UNIVERSE = ["ETH/AUD", "LINK/AUD", "ADA/AUD", "SOL/AUD"]


def _sydney_midnight_utc() -> str:
    """ISO timestamp for today's 00:00 Australia/Sydney, expressed in UTC."""
    now_syd = datetime.now(SYDNEY)
    start = datetime.combine(now_syd.date(), time(0, 0), tzinfo=SYDNEY)
    return start.astimezone(timezone.utc).isoformat()


def _find_dca() -> dict:
    from backend.db.supabase_client import get_supabase
    sb = get_supabase()
    r = (sb.schema("public").table("strategies")
           .select("id,name,deterministic_config,trigger_config")
           .eq("name", "DCA-Baseline").limit(1).execute())
    if not r.data:
        raise SystemExit("DCA-Baseline strategy not found — run seed_strategies first.")
    return r.data[0]


def _sync_cadence_to_tuesday(row: dict) -> bool:
    """Update the live row's cron to Tuesday. Returns True if anything changed."""
    from backend.db.supabase_client import get_supabase
    sb = get_supabase()

    det = dict(row.get("deterministic_config") or {})
    trig = dict(row.get("trigger_config") or {})
    triggers = [dict(t) for t in (trig.get("triggers") or [])]

    changed = False
    if det.get("cadence_cron") != TUESDAY_CRON:
        det["cadence_cron"] = TUESDAY_CRON
        changed = True
    for t in triggers:
        if t.get("type") == "cron" and t.get("expr") != TUESDAY_CRON:
            t["expr"] = TUESDAY_CRON
            changed = True
    trig["triggers"] = triggers

    if changed:
        sb.schema("public").table("strategies").update(
            {"deterministic_config": det, "trigger_config": trig}
        ).eq("id", row["id"]).execute()
        logger.info("DCA cadence re-pointed to Tuesdays (%s) — active on next deploy.",
                    TUESDAY_CRON)
    else:
        logger.info("DCA cadence already on Tuesdays (%s) — no change.", TUESDAY_CRON)
    return changed


def _already_fired_today(strategy_id: str) -> bool:
    from backend.db.supabase_client import get_supabase
    sb = get_supabase()
    since = _sydney_midnight_utc()
    r = (sb.schema("public").table("agent_decisions")
           .select("id", count="exact")
           .eq("strategy_id", strategy_id)
           .gte("created_at", since)
           .execute())
    return bool(r.count)


async def _fire_one_slice(strategy_id: str) -> None:
    from backend.repositories import strategies_repo
    from backend.models.trading import CronTriggerEvent
    from backend.services.trading.event_bus import get_default_bus
    from backend.services.trading.executor import PaperExecutor
    from backend.services.trading.price_feed import PriceFeed, wait_for_books
    from backend.services.trading.strategy_loop import (
        invoke_deterministic_strategy, set_executor,
    )
    from uuid import UUID

    strat = strategies_repo.get(UUID(strategy_id))
    if strat is None:
        raise SystemExit("DCA-Baseline row vanished between lookup and fire.")

    bus = get_default_bus()
    executor = PaperExecutor()
    set_executor(executor)
    feed = PriceFeed(pairs=UNIVERSE, bus=bus, executor=executor)
    feed_task = asyncio.create_task(feed.run(), name="dca_feed")
    try:
        logger.info("Warming order books over Kraken WS (up to 30s)...")
        warmed = await wait_for_books(executor, UNIVERSE, timeout_s=30.0)
        if not warmed:
            raise SystemExit("Books did not warm within 30s — aborting (no fire).")
        logger.info("Books warm. Firing DCA slice now.")
        event = CronTriggerEvent(
            expr=TUESDAY_CRON, ts=datetime.now(timezone.utc), strategy_id=strategy_id,
        )
        await invoke_deterministic_strategy(strat, event)
        logger.info("DCA slice fired. Orders written to paper_orders for %s.", strat.name)
    finally:
        feed_task.cancel()
        try:
            await feed_task
        except asyncio.CancelledError:
            pass


async def main() -> None:
    row = _find_dca()
    _sync_cadence_to_tuesday(row)

    if _already_fired_today(row["id"]):
        logger.info("A DCA-Baseline decision already exists for today (Sydney) — "
                    "skipping the fire to avoid double-spending a slice.")
        return

    await _fire_one_slice(row["id"])


if __name__ == "__main__":
    asyncio.run(main())
