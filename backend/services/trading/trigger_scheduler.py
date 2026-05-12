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

            async def _fire(expr=t["expr"]):
                await bus.publish(CronTriggerEvent(
                    expr=expr, ts=datetime.now(timezone.utc),
                ))
            scheduler.add_job(
                _fire, ct, id=f"strat-{strategy.id}-cron-{t['expr']}",
                replace_existing=True,
            )
        else:
            it = IntervalTrigger(minutes=t["minutes"])

            async def _fire(minutes=t["minutes"]):
                await bus.publish(IntervalTriggerEvent(
                    minutes=minutes, ts=datetime.now(timezone.utc),
                ))
            scheduler.add_job(
                _fire, it,
                id=f"strat-{strategy.id}-interval-{t['minutes']}",
                replace_existing=True,
            )
    logger.info("Registered triggers for strategy %s", strategy.name)
