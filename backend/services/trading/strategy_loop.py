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


# Re-export for monkeypatching in tests; real implementation in llm_strategy.py.
async def invoke_llm_strategy(strategy: StrategyRow, event) -> None:
    from backend.services.trading.llm_strategy import (
        invoke_llm_strategy as _invoke,
    )
    await _invoke(strategy, event)


# Module-level executor handle, set by main.py at boot (Task 31). Tests can
# also assign a fake here.
_current_executor = None
# Module-level schema; main.py uses "public", tests can set to "test".
_current_schema: str = "public"


def set_executor(executor, *, schema: str = "public") -> None:
    global _current_executor, _current_schema
    _current_executor = executor
    _current_schema = schema


async def invoke_deterministic_strategy(strategy: StrategyRow, event) -> None:
    """Deterministic execution path — spec §6.4."""
    from decimal import Decimal
    from time import perf_counter
    from backend.repositories import paper_positions_repo
    from backend.services.trading.deterministic import compute_rebalance_orders
    from backend.services.trading.decision_writer import write_agent_decision

    started = perf_counter()
    cfg = strategy.deterministic_config
    if cfg is None:
        raise ValueError(f"Strategy {strategy.name} is deterministic but has no config")

    # Snapshot current position values using attached book mids.
    rows = paper_positions_repo.get_all(strategy.id, schema=_current_schema)
    mids: dict[str, Decimal] = {}
    positions_aud: dict[str, Decimal] = {}
    for asset, row in rows.items():
        qty = Decimal(row["qty"])
        if asset == "AUD":
            positions_aud[asset] = qty
            continue
        pair = f"{asset}/AUD"
        book = (_current_executor._books.get(pair)
                if _current_executor is not None and hasattr(_current_executor, "_books")
                else None)
        if book is None:
            mids[pair] = Decimal(row.get("avg_cost_aud") or "0")
        else:
            mids[pair] = book.mid()
        positions_aud[asset] = qty * mids[pair]

    # For first-time runs the mids dict only has entries for assets we already
    # hold; populate it for the target pairs too, defaulting to 1 if unknown.
    for pair in cfg.allocations:
        mids.setdefault(pair, Decimal("1"))

    target_orders = compute_rebalance_orders(
        positions_aud=positions_aud,
        target_weights=cfg.allocations,
        starting_balance_aud=strategy.starting_balance_aud,
        mids=mids,
    )

    decision_id = write_agent_decision(
        strategy_id=strategy.id, execution_mode="deterministic",
        # mode='json' coerces datetime → ISO string so JSONB serialisation works.
        trigger_event=(event.model_dump(mode="json") if hasattr(event, "model_dump")
                       else dict(event)),
        input_snapshot={"positions_aud": {k: str(v) for k, v in positions_aud.items()},
                        "mids": {k: str(v) for k, v in mids.items()}},
        persona_prompt_hash=None, model=None,
        input_tokens=0, output_tokens=0, cost_aud=Decimal("0"),
        tool_calls=[{"tool": "place_paper_order",
                     "args": {"pair": o.pair, "side": o.side,
                              "notional_aud": str(o.notional_aud)}}
                    for o in target_orders],
        agent_output=None,
        latency_ms=int((perf_counter() - started) * 1000),
        error=None,
        schema=_current_schema,
    )

    if strategy.dry_run or _current_executor is None:
        return

    for seq, o in enumerate(target_orders):
        # Convert notional → qty at current mid.
        mid = mids.get(o.pair) or Decimal("1")
        qty = (o.notional_aud / mid)
        await _current_executor.submit_order(
            strategy_id=strategy.id,
            idempotency_key=f"{strategy.id}:{decision_id}:{seq}",
            pair=o.pair, side=o.side, type="market", qty=qty,
        )


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
