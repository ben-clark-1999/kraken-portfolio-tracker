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


def _book_for(pair: str):
    if _current_executor is not None and hasattr(_current_executor, "_books"):
        return _current_executor._books.get(pair)
    return None


async def invoke_deterministic_strategy(strategy: StrategyRow, event) -> None:
    """Deterministic execution path (spec §3.1 / §3.7).

    Branches on deterministic_config.mode:
      - 'rebalance'             → target-weight rebalancer (original)
      - 'dca'                   → fixed-slice weekly DCA
      - 'trend_rule'            → 24h breakout matched-twin
      - 'mean_reversion_rule'   → 48h z-score matched-twin
    Every target order is split under the per-order cap before submission.
    """
    import asyncio
    from decimal import Decimal
    from statistics import mean as _mean, pstdev as _pstdev
    from time import perf_counter

    from backend.repositories import paper_positions_repo
    from backend.services import kraken_service
    from backend.services.trading.deterministic import (
        compute_dca_orders, compute_rebalance_orders, compute_rule_targets,
        mean_reversion_signal, split_order, trend_signal,
    )
    from backend.services.trading.decision_writer import write_agent_decision

    started = perf_counter()
    cfg = strategy.deterministic_config
    if cfg is None:
        raise ValueError(f"Strategy {strategy.name} is deterministic but has no config")

    target_pairs = cfg.universe or list(cfg.allocations.keys())

    # ── Snapshot positions + resolve a mid for every target pair ──────
    rows = paper_positions_repo.get_all(strategy.id, schema=_current_schema)
    mids: dict[str, Decimal] = {}
    positions_aud: dict[str, Decimal] = {}
    held: set[str] = set()
    for asset, row in rows.items():
        qty = Decimal(str(row["qty"]))
        if asset == "AUD":
            positions_aud[asset] = qty
            continue
        pair = f"{asset}/AUD"
        book = _book_for(pair)
        mids[pair] = book.mid() if book is not None else Decimal(str(row.get("avg_cost_aud") or "0"))
        positions_aud[asset] = qty * mids[pair]
        if qty > 0 and pair in target_pairs:
            held.add(pair)

    for pair in target_pairs:
        if pair in mids:
            continue
        book = _book_for(pair)
        if book is not None and book.bids and book.asks:
            mids[pair] = book.mid()

    missing = [p for p in target_pairs if p not in mids]
    if missing:
        try:
            from backend.services.trading.min_order import fetch_last_prices
            for p, v in fetch_last_prices(missing).items():
                mids[p] = v
        except Exception:
            logger.exception("Deterministic %s: REST price fallback failed", strategy.name)
        missing = [p for p in target_pairs if p not in mids]
        if missing:
            logger.warning("Deterministic %s: cannot price %s — skipping",
                           strategy.name, ",".join(missing))
            return

    # ── Build target orders per mode ──────────────────────────────────
    cash = positions_aud.get("AUD", Decimal("0"))
    if cfg.mode == "dca":
        if not cfg.num_buys:
            raise ValueError(f"{strategy.name}: dca mode requires num_buys")
        slice_total = strategy.starting_balance_aud / Decimal(cfg.num_buys)
        target_orders = compute_dca_orders(
            cash_aud=cash, slice_total=slice_total, weights=cfg.allocations)
    elif cfg.mode in ("trend_rule", "mean_reversion_rule"):
        enter: set[str] = set()
        exit_: set[str] = set()
        for pair in cfg.universe:
            try:
                bars = await asyncio.to_thread(kraken_service.get_ohlc_hourly, pair, 48)
            except Exception:
                logger.exception("Deterministic %s: OHLC fetch failed for %s — skipping pair",
                                 strategy.name, pair)
                continue
            closes = [Decimal(str(b["close"])) for b in bars]
            if len(closes) < 2:
                continue
            if cfg.mode == "trend_rule":
                sig = trend_signal(current_price=mids[pair], closes=closes,
                                   lookback_bars=24, min_move_pct=cfg.min_move_pct)
                if sig == "long":
                    enter.add(pair)
                elif sig == "exit":
                    exit_.add(pair)
            else:
                fcloses = [float(c) for c in closes]
                sd = _pstdev(fcloses)
                if sd <= 0:
                    continue
                z = Decimal(str((float(mids[pair]) - _mean(fcloses)) / sd))
                sig = mean_reversion_signal(z=z, entry_z=cfg.entry_z, exit_z=cfg.exit_z)
                if sig == "buy":
                    enter.add(pair)
                elif sig == "exit":
                    exit_.add(pair)
        targets = compute_rule_targets(
            enter=enter, exit_=exit_, universe=cfg.universe, held=held)
        if targets is None:
            target_orders = []
        else:
            target_orders = compute_rebalance_orders(
                positions_aud=positions_aud, target_weights=targets,
                starting_balance_aud=strategy.starting_balance_aud, mids=mids)
    else:  # 'rebalance'
        target_orders = compute_rebalance_orders(
            positions_aud=positions_aud, target_weights=cfg.allocations,
            starting_balance_aud=strategy.starting_balance_aud, mids=mids)

    # ── Split oversized orders under the per-order cap (spec §3.7) ─────
    cap = strategy.risk_caps.max_order_aud
    split_orders = [s for o in target_orders for s in split_order(order=o, max_order_aud=cap)]

    decision_id = write_agent_decision(
        strategy_id=strategy.id, execution_mode="deterministic",
        trigger_event=(event.model_dump(mode="json") if hasattr(event, "model_dump") else dict(event)),
        input_snapshot={"positions_aud": {k: str(v) for k, v in positions_aud.items()},
                        "mids": {k: str(v) for k, v in mids.items()},
                        "mode": cfg.mode},
        persona_prompt_hash=None, model=None,
        input_tokens=0, output_tokens=0, cost_aud=Decimal("0"),
        tool_calls=[{"tool": "place_paper_order",
                     "args": {"pair": o.pair, "side": o.side, "notional_aud": str(o.notional_aud)}}
                    for o in split_orders],
        agent_output=None, latency_ms=int((perf_counter() - started) * 1000),
        error=None, schema=_current_schema,
    )

    if strategy.dry_run or _current_executor is None:
        return

    for seq, o in enumerate(split_orders):
        mid = mids.get(o.pair)
        if mid is None or mid <= 0:
            raise RuntimeError(
                f"No mid for {o.pair} at submission time — refusing to convert "
                f"notional {o.notional_aud} to qty")
        await _current_executor.submit_order(
            strategy_id=strategy.id,
            idempotency_key=f"{strategy.id}:{decision_id}:{seq}",
            pair=o.pair, side=o.side, type="market", qty=(o.notional_aud / mid),
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
    # Scheduled triggers (cron/interval) carry the id of the strategy that
    # owns them, so a fire only wakes that strategy. Without this, every
    # strategy interested in the 'cron' type would wake on every cron tick —
    # e.g. the daily rule strategies' 09:00 tick would also fire weekly DCA,
    # turning it into daily DCA and corrupting the baseline. Events with no
    # owner tag (older callers / tests) fall back to type matching.
    sid = getattr(event, "strategy_id", None)
    if sid is not None and event.type in ("cron", "interval"):
        return str(sid) == str(strategy.id)
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
