"""Per-strategy asyncio loop.

Spec §6.1 — note the conditional throttling: only `llm_agent` strategies
go through should_fire(). Deterministic strategies fire on every relevant
event (they're cheap, predictable, and must run on schedule).
"""
from __future__ import annotations

import logging

from backend.models.trading import StrategyRow
from backend.services.trading.event_bus import EventBus, get_default_bus
from backend.services.trading.trigger_state import TriggerConfig, TriggerState

logger = logging.getLogger(__name__)


# Re-export for monkeypatching in tests; real implementations land in
# tasks 20 and 24.
async def invoke_llm_strategy(strategy: StrategyRow, event) -> None:
    raise NotImplementedError("wired in Task 24")


async def invoke_deterministic_strategy(strategy: StrategyRow, event) -> None:
    raise NotImplementedError("wired in Task 20")


async def emergency_stop(strategy: StrategyRow, exc: BaseException) -> None:
    from backend.repositories import strategies_repo
    logger.exception("Strategy %s crashed — pausing", strategy.name)
    strategies_repo.update_status(strategy.id, "paused")
    try:
        from backend.repositories import system_alerts_repo as alerts
        alerts.insert(
            level="error", code="STRATEGY_AUTO_PAUSED_EXCEPTION",
            strategy_id=strategy.id,
            message=f"{strategy.name}: {exc!r}",
            payload={"exception": str(exc)},
        )
    except Exception:
        # Best-effort — alert insertion failing shouldn't compound the issue.
        pass


def _event_matches_strategy(event, strategy: StrategyRow) -> bool:
    triggers = (strategy.trigger_config or {}).get("triggers", [])
    interested_types = {t["type"] for t in triggers}
    return event.type in interested_types


async def strategy_loop(
    strategy: StrategyRow,
    *,
    bus: EventBus | None = None,
    max_iterations: int | None = None,
) -> None:
    bus = bus or get_default_bus()
    state = TriggerState()
    cfg_dict = strategy.trigger_config or {}
    config = TriggerConfig(
        debounce_seconds=cfg_dict.get("debounce_seconds", 5),
        cooldown_seconds=cfg_dict.get("cooldown_seconds", 900),
        max_calls_per_hour=cfg_dict.get("max_calls_per_hour", 10),
    )
    iterations = 0
    async for event in bus.subscribe():
        if strategy.status != "active":
            return
        if not _event_matches_strategy(event, strategy):
            continue
        if strategy.execution_mode == "llm_agent":
            if not state.should_fire(event_ts=event.ts, config=config):
                continue
            state.record_invocation(event.ts)
        try:
            if strategy.execution_mode == "llm_agent":
                await invoke_llm_strategy(strategy, event)
            else:
                await invoke_deterministic_strategy(strategy, event)
        except Exception as exc:
            await emergency_stop(strategy, exc)
        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            return
