import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from backend.models.trading import (
    CronTriggerEvent, IntervalTriggerEvent, RiskCaps, KillCriteria,
    StrategyRow,
)
from backend.services.trading.event_bus import EventBus
from backend.services.trading.strategy_loop import strategy_loop


def _strategy(execution_mode="llm_agent"):
    return StrategyRow(
        id=uuid4(), name="x", execution_mode=execution_mode,
        persona_key="trend-follower" if execution_mode == "llm_agent" else None,
        deterministic_config=None,
        starting_balance_aud=Decimal("1000"),
        trigger_config={"triggers": [{"type": "interval", "minutes": 60}],
                        "debounce_seconds": 0, "cooldown_seconds": 0,
                        "max_calls_per_hour": 100},
        risk_caps=RiskCaps(), kill_criteria=KillCriteria(),
        status="active", dry_run=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_loop_invokes_llm_path_on_matching_event(monkeypatch):
    bus = EventBus()
    invoked = []

    async def fake_llm(strategy, event):
        invoked.append(("llm", strategy.id, event.type))

    async def fake_det(strategy, event):
        invoked.append(("det", strategy.id, event.type))

    monkeypatch.setattr(
        "backend.services.trading.strategy_loop.invoke_llm_strategy", fake_llm)
    monkeypatch.setattr(
        "backend.services.trading.strategy_loop.invoke_deterministic_strategy", fake_det)

    strat = _strategy("llm_agent")
    task = asyncio.create_task(strategy_loop(strat, bus=bus, max_iterations=1))
    await asyncio.sleep(0.01)
    await bus.publish(IntervalTriggerEvent(minutes=60,
                                            ts=datetime.now(timezone.utc)))
    await asyncio.wait_for(task, timeout=2.0)
    assert invoked and invoked[0][0] == "llm"


@pytest.mark.asyncio
async def test_loop_invokes_deterministic_path_when_mode_is_deterministic(monkeypatch):
    bus = EventBus()
    invoked = []

    async def fake_llm(s, e): invoked.append("llm")
    async def fake_det(s, e): invoked.append("det")

    monkeypatch.setattr(
        "backend.services.trading.strategy_loop.invoke_llm_strategy", fake_llm)
    monkeypatch.setattr(
        "backend.services.trading.strategy_loop.invoke_deterministic_strategy", fake_det)

    # Deterministic strategy needs cron triggers to match the cron event.
    strat = _strategy("deterministic")
    strat.trigger_config = {"triggers": [{"type": "cron", "expr": "0 9 * * *"}],
                            "debounce_seconds": 0, "cooldown_seconds": 0,
                            "max_calls_per_hour": 100}
    task = asyncio.create_task(strategy_loop(strat, bus=bus, max_iterations=1))
    await asyncio.sleep(0.01)
    await bus.publish(CronTriggerEvent(expr="0 9 * * *",
                                       ts=datetime.now(timezone.utc)))
    await asyncio.wait_for(task, timeout=2.0)
    assert invoked == ["det"]


@pytest.mark.asyncio
async def test_loop_exception_pauses_strategy_and_continues(monkeypatch):
    bus = EventBus()
    paused = []

    async def broken_llm(strategy, event):
        raise RuntimeError("boom")

    async def fake_emergency_stop(strategy, exc):
        paused.append((strategy.id, str(exc)))

    monkeypatch.setattr(
        "backend.services.trading.strategy_loop.invoke_llm_strategy", broken_llm)
    monkeypatch.setattr(
        "backend.services.trading.strategy_loop.emergency_stop", fake_emergency_stop)

    strat = _strategy("llm_agent")
    task = asyncio.create_task(strategy_loop(strat, bus=bus, max_iterations=1))
    await asyncio.sleep(0.01)
    await bus.publish(IntervalTriggerEvent(minutes=60,
                                            ts=datetime.now(timezone.utc)))
    await asyncio.wait_for(task, timeout=2.0)
    assert paused and "boom" in paused[0][1]
