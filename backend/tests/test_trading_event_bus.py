import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.models.trading import IntervalTriggerEvent, TickEvent
from backend.services.trading.event_bus import EventBus


@pytest.mark.asyncio
async def test_publish_then_subscribe_receives_event():
    bus = EventBus()
    received: list = []

    async def consumer():
        async for evt in bus.subscribe():
            received.append(evt)
            if len(received) >= 1:
                break

    task = asyncio.create_task(consumer())
    await asyncio.sleep(0.01)
    await bus.publish(TickEvent(pair="ETH/AUD", price=Decimal("100"),
                                ts=datetime.now(timezone.utc)))
    await asyncio.wait_for(task, timeout=1.0)
    assert received[0].type == "tick"


@pytest.mark.asyncio
async def test_multiple_subscribers_each_receive_independent_stream():
    bus = EventBus()
    a: list = []
    b: list = []

    async def consume(into):
        async for evt in bus.subscribe():
            into.append(evt)
            if len(into) >= 2:
                break

    ta = asyncio.create_task(consume(a))
    tb = asyncio.create_task(consume(b))
    await asyncio.sleep(0.01)
    for i in range(2):
        await bus.publish(IntervalTriggerEvent(minutes=60,
                                               ts=datetime.now(timezone.utc)))
    await asyncio.gather(ta, tb)
    assert len(a) == 2 and len(b) == 2


@pytest.mark.asyncio
async def test_subscribe_with_filter_only_passes_matching_events():
    bus = EventBus()
    only_ticks: list = []

    async def consume():
        async for evt in bus.subscribe(filter_fn=lambda e: e.type == "tick"):
            only_ticks.append(evt)
            if len(only_ticks) >= 1:
                break

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.01)
    await bus.publish(IntervalTriggerEvent(minutes=60, ts=datetime.now(timezone.utc)))
    await bus.publish(TickEvent(pair="ETH/AUD", price=Decimal("100"),
                                ts=datetime.now(timezone.utc)))
    await asyncio.wait_for(task, timeout=1.0)
    assert only_ticks[0].type == "tick"
