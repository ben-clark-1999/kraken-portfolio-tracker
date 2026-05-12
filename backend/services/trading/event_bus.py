"""In-process pub/sub bus. Backing store: per-subscriber asyncio.Queue.

Spec §3 (architecture). Approach A v1; Approach B swaps this for
Postgres LISTEN/NOTIFY without changing publishers/subscribers.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator, Callable


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    async def publish(self, event) -> None:
        async with self._lock:
            queues = list(self._subscribers)
        for q in queues:
            await q.put(event)

    async def subscribe(
        self, *, filter_fn: Callable[[object], bool] | None = None,
    ) -> AsyncIterator:
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        async with self._lock:
            self._subscribers.append(q)
        try:
            while True:
                evt = await q.get()
                if filter_fn is None or filter_fn(evt):
                    yield evt
        finally:
            async with self._lock:
                if q in self._subscribers:
                    self._subscribers.remove(q)


_default_bus: EventBus | None = None


def get_default_bus() -> EventBus:
    global _default_bus
    if _default_bus is None:
        _default_bus = EventBus()
    return _default_bus
