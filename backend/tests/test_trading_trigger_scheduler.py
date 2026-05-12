import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.models.trading import StrategyRow, RiskCaps, KillCriteria
from backend.services.trading.event_bus import EventBus
from backend.services.trading.trigger_scheduler import (
    register_strategy_triggers, _build_jobs_for_strategy,
)


def _strategy(name="trend-follower", triggers=None):
    return StrategyRow(
        id="00000000-0000-0000-0000-000000000001",
        name=name, execution_mode="llm_agent",
        persona_key=name, deterministic_config=None,
        starting_balance_aud=Decimal("1000"),
        trigger_config={"triggers": triggers or [
            {"type": "interval", "minutes": 60},
            {"type": "cron", "expr": "0 9 * * *", "tz": "Australia/Sydney"},
        ], "debounce_seconds": 5, "cooldown_seconds": 900,
         "max_calls_per_hour": 10},
        risk_caps=RiskCaps(), kill_criteria=KillCriteria(),
        status="active", dry_run=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_build_jobs_for_strategy_returns_one_per_trigger():
    jobs = _build_jobs_for_strategy(_strategy())
    assert len(jobs) == 2
    kinds = {j[0] for j in jobs}
    assert kinds == {"interval", "cron"}


@pytest.mark.asyncio
async def test_register_publishes_event_on_interval_fire():
    bus = EventBus()
    scheduler = AsyncIOScheduler()
    scheduler.start()
    register_strategy_triggers(_strategy(triggers=[
        {"type": "interval", "minutes": 60},
    ]), scheduler=scheduler, bus=bus)
    received = []

    async def consume():
        async for evt in bus.subscribe():
            received.append(evt)
            break

    consumer = asyncio.create_task(consume())
    # Let the consumer subscribe before we publish (otherwise the event
    # has no subscribers and is dropped — see EventBus.publish).
    await asyncio.sleep(0.01)
    # Manually fire the registered job rather than waiting an hour.
    [job] = scheduler.get_jobs()
    await job.func()
    await asyncio.wait_for(consumer, timeout=1.0)
    scheduler.shutdown()
    assert received and received[0].type == "interval"
