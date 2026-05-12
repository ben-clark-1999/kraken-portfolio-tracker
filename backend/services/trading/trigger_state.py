"""Per-strategy throttling state — debounce, cooldown, rate cap.

Spec §6.3. Only applies to llm_agent strategies (the strategy loop
skips invoking should_fire for deterministic strategies — spec §6.1).
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class TriggerConfig:
    debounce_seconds: int = 5
    cooldown_seconds: int = 900
    max_calls_per_hour: int = 10


@dataclass
class TriggerState:
    last_invocation_at: datetime | None = None
    last_event_at: datetime | None = None
    invocations_window: deque = field(default_factory=lambda: deque(maxlen=60))

    def should_fire(self, *, event_ts: datetime, config: TriggerConfig) -> bool:
        # Debounce: ignore events within `debounce_seconds` of the previous event.
        if (self.last_event_at is not None
                and (event_ts - self.last_event_at).total_seconds()
                    < config.debounce_seconds):
            return False
        # Cooldown: don't invoke if we just invoked.
        if (self.last_invocation_at is not None
                and (event_ts - self.last_invocation_at).total_seconds()
                    < config.cooldown_seconds):
            self.last_event_at = event_ts
            return False
        # Rate cap: count invocations in last 60 min.
        cutoff = event_ts - timedelta(hours=1)
        recent = sum(1 for ts in self.invocations_window if ts > cutoff)
        if recent >= config.max_calls_per_hour:
            self.last_event_at = event_ts
            return False
        self.last_event_at = event_ts
        return True

    def record_invocation(self, ts: datetime) -> None:
        self.last_invocation_at = ts
        self.invocations_window.append(ts)
