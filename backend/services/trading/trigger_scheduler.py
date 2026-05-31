
"""Bridge between APScheduler and the EventBus for cron/interval triggers.

Each strategy's cron/interval triggers are registered as APScheduler jobs
that fire async callables which publish CronTriggerEvent / IntervalTriggerEvent
onto the bus. The strategy_loop_task then filters and consumes from the bus.

Spec §6.2.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.models.trading import (
    CronTriggerEvent, IntervalTriggerEvent, StrategyRow,
)
from backend.services.trading.event_bus import EventBus, get_default_bus

logger = logging.getLogger(__name__)


def _build_jobs_for_strategy(
    strategy: StrategyRow,
) -> list[tuple[Literal["cron", "interval"], dict]]:
    triggers = (strategy.trigger_config or {}).get("triggers", [])
    return [(t["type"], t) for t in triggers if t["type"] in ("cron", "interval")]


def register_strategy_triggers(
    strategy: StrategyRow,
    *,
    scheduler: AsyncIOScheduler,
    bus: EventBus | None = None,
) -> None:
    bus = bus or get_default_bus()
    for kind, t in _build_jobs_for_strategy(strategy):
        if kind == "cron":
            ct = CronTrigger.from_crontab(t["expr"], timezone=t.get("tz", "UTC"))

            async def _fire(expr=t["expr"], sid=str(strategy.id)):
                await bus.publish(CronTriggerEvent(
                    expr=expr, ts=datetime.now(timezone.utc), strategy_id=sid,
                ))
            scheduler.add_job(
                _fire, ct, id=f"strat-{strategy.id}-cron-{t['expr']}",
                replace_existing=True,
            )
        else:
            # Anchor the fire-grid to the strategy's created_at (a fixed point
            # in the past) instead of letting APScheduler default start_date to
            # "now". Otherwise every app restart re-registers the job with
            # next_run = now + interval, so a frequently-restarted server (e.g.
            # uvicorn --reload locally) keeps pushing a 12h interval out and it
            # may never fire. A fixed anchor makes the schedule deterministic:
            # a restart resumes the same grid, with the next fire at most one
            # interval away. coalesce + misfire_grace_time let a slot missed
            # during a brief downtime (laptop sleep) still fire once on resume.
            it = IntervalTrigger(
                minutes=t["minutes"],
                start_date=strategy.created_at,
                timezone=timezone.utc,
            )

            async def _fire(minutes=t["minutes"], sid=str(strategy.id)):
                await bus.publish(IntervalTriggerEvent(
                    minutes=minutes, ts=datetime.now(timezone.utc), strategy_id=sid,
                ))
            scheduler.add_job(
                _fire, it,
                id=f"strat-{strategy.id}-interval-{t['minutes']}",
                replace_existing=True,
                coalesce=True, misfire_grace_time=3600,
            )
    logger.info("Registered triggers for strategy %s", strategy.name)
