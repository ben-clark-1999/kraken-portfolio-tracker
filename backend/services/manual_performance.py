"""Pure-function TWR + synthetic-unit equity-curve construction.

No DB, no HTTP. Inputs are raw equity points and cash-flow events
(at arbitrary timestamps); the function merges them chronologically
and segments at every cash flow internally. The synthetic_unit_curve
feeds the existing metrics.sharpe_24_7 / metrics.max_drawdown_pct
functions so the manual portfolio's risk numbers are computed the
same way as paper strategies.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class EquityPoint:
    captured_at: datetime
    total_value_aud: Decimal


@dataclass(frozen=True)
class CashFlowEvent:
    occurred_at: datetime
    amount_aud: Decimal              # always positive; direction is in `kind`
    kind: str                        # "deposit" | "withdrawal"


def compute_twr(
    equity_curve: list[EquityPoint],
    cash_flows: list[CashFlowEvent],
) -> tuple[Decimal, list[Decimal]]:
    """Return (twr_pct, synthetic_unit_curve).

    Inputs are raw — snapshots and cash flows at independent timestamps.
    The function merges them chronologically and segments at every cash
    flow internally. Cash flows that pre-date the first snapshot are
    ignored (no baseline to attribute them against).

    twr_pct is expressed as a percent (e.g., +10% → Decimal("10.00")).
    The synthetic_unit_curve has one entry per snapshot (cash flows
    don't add curve points — they only modify the segment factor).
    """
    if not equity_curve:
        return Decimal("0"), [Decimal("1")]

    # Merge into a chronological event stream. Tie-break: when a snapshot
    # and a cash flow share a timestamp, process the snapshot FIRST
    # (the snap represents the pre-cash-flow value).
    events: list[tuple[datetime, int, object]] = []
    for ep in equity_curve:
        events.append((ep.captured_at, 0, ep))      # 0 = snap, sorts before flow
    for cf in cash_flows:
        events.append((cf.occurred_at, 1, cf))      # 1 = flow
    events.sort(key=lambda e: (e[0], e[1]))

    unit_curve: list[Decimal] = []
    twr_factor = Decimal("1")
    seg_start: Decimal | None = None
    last_value: Decimal | None = None

    for ts, kind_code, obj in events:
        if kind_code == 0:  # snapshot
            ep = obj  # type: ignore[assignment]
            if seg_start is None:
                # First snapshot — initialise the first segment.
                seg_start = ep.total_value_aud
                last_value = ep.total_value_aud
                unit_curve.append(Decimal("1"))
            else:
                last_value = ep.total_value_aud
                if seg_start > 0:
                    running = twr_factor * (last_value / seg_start)
                else:
                    running = Decimal("0")
                unit_curve.append(running.quantize(Decimal("0.000001")))
        else:  # cash flow
            cf = obj  # type: ignore[assignment]
            if seg_start is None or last_value is None:
                # Cash flow before any snapshot. No baseline; skip silently.
                continue
            # Close the current segment at last_value.
            if seg_start > 0:
                seg_return = last_value / seg_start
            else:
                seg_return = Decimal("0")
            twr_factor = twr_factor * seg_return
            # Start a new segment at last_value + signed delta.
            delta = (cf.amount_aud if cf.kind == "deposit"
                     else -cf.amount_aud)
            new_seg_start = last_value + delta
            if new_seg_start <= 0:
                # Portfolio drained mid-window. Lock the unit curve at 0
                # for any remaining snapshots and return -100%.
                remaining = len(equity_curve) - len(unit_curve)
                for _ in range(remaining):
                    unit_curve.append(Decimal("0"))
                return (twr_factor - Decimal("1")) * Decimal("100"), unit_curve
            seg_start = new_seg_start
            last_value = new_seg_start

    # Close the final segment.
    if seg_start is not None and seg_start > 0 and last_value is not None:
        final_return = last_value / seg_start
    else:
        final_return = Decimal("0")
    twr_total = twr_factor * final_return
    twr_pct = (twr_total - Decimal("1")) * Decimal("100")
    return twr_pct.quantize(Decimal("0.01")), unit_curve
