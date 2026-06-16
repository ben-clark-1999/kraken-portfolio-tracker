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


def test_scheduled_event_only_wakes_owning_strategy():
    """A cron/interval fire must only wake the strategy that owns it. Without
    owner-scoping, a daily-cron strategy's 09:00 tick also woke any other
    strategy interested in the 'cron' type — turning weekly DCA into daily DCA
    and corrupting the baseline."""
    from backend.services.trading.strategy_loop import _event_matches_strategy

    weekly = _strategy("deterministic")
    weekly.trigger_config = {"triggers": [{"type": "cron", "expr": "0 9 * * 1"}]}
    daily = _strategy("deterministic")
    daily.trigger_config = {"triggers": [{"type": "cron", "expr": "0 9 * * *"}]}

    # This event was fired by `daily`'s trigger (tagged with its id):
    evt = CronTriggerEvent(expr="0 9 * * *", ts=datetime.now(timezone.utc),
                           strategy_id=str(daily.id))
    assert _event_matches_strategy(evt, daily) is True
    assert _event_matches_strategy(evt, weekly) is False

    # Back-compat: an untagged event still matches by type.
    untagged = CronTriggerEvent(expr="0 9 * * *", ts=datetime.now(timezone.utc))
    assert _event_matches_strategy(untagged, weekly) is True


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


@pytest.mark.asyncio
async def test_loop_transient_network_error_does_not_pause(monkeypatch):
    """A transient network blip (httpx read/connect timeout) must NOT auto-pause
    the strategy — it should be logged and the tick skipped, so a single
    timeout doesn't permanently kill a strategy mid-experiment. This is the
    root cause of the Mean-Reversion-Rule pause: one ReadTimeout on 2026-06-03
    auto-paused it for two weeks."""
    import httpx

    bus = EventBus()
    paused = []

    async def flaky_llm(strategy, event):
        raise httpx.ReadTimeout("The read operation timed out")

    async def fake_emergency_stop(strategy, exc):
        paused.append((strategy.id, str(exc)))

    monkeypatch.setattr(
        "backend.services.trading.strategy_loop.invoke_llm_strategy", flaky_llm)
    monkeypatch.setattr(
        "backend.services.trading.strategy_loop.emergency_stop", fake_emergency_stop)

    strat = _strategy("llm_agent")
    task = asyncio.create_task(strategy_loop(strat, bus=bus, max_iterations=1))
    await asyncio.sleep(0.01)
    await bus.publish(IntervalTriggerEvent(minutes=60,
                                            ts=datetime.now(timezone.utc)))
    await asyncio.wait_for(task, timeout=2.0)
    assert paused == [], "transient network error must not pause the strategy"
