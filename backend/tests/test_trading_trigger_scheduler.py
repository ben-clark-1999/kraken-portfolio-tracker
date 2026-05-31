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


def test_interval_trigger_anchored_to_created_at_grid():
    """Restart-safety (Finding 2): the interval fire-grid is anchored to the
    strategy's created_at, not to boot time. Without this, each app restart
    (e.g. uvicorn --reload) re-registers the job with next_run = now + interval,
    so a 12h interval could be pushed out indefinitely and never fire."""
    from datetime import timedelta

    created = datetime(2026, 5, 30, 8, 18, 33, tzinfo=timezone.utc)
    strat = _strategy(triggers=[{"type": "interval", "minutes": 720}])
    strat = strat.model_copy(update={"created_at": created})

    scheduler = AsyncIOScheduler()
    register_strategy_triggers(strat, scheduler=scheduler, bus=EventBus())
    [job] = scheduler.get_jobs()

    interval = timedelta(minutes=720)
    assert job.trigger.interval == interval
    # The next fire after ANY boot time lands on the created_at grid, so two
    # different restart times yield the same grid-aligned schedule rather than
    # boot-relative ones.
    for boot in (created + timedelta(hours=3), created + timedelta(hours=27)):
        nxt = job.trigger.get_next_fire_time(None, boot)
        assert (nxt - created) % interval == timedelta(0), (
            f"next fire {nxt} is not on the created_at grid for boot={boot}"
        )
        assert nxt > boot


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
