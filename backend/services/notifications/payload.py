"""Pure-function rendering of ntfy notification payloads.

No DB, no HTTP. Inputs are normalised dataclasses; output is a dict
matching ntfy's JSON-publish schema (https://ntfy.sh/docs/publish/).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

Side = Literal["buy", "sell"]
MAX_VISIBLE_LEGS = 4


@dataclass(frozen=True)
class NotificationLeg:
    side: Side
    pair: str                       # e.g. "ETH/AUD"
    notional_aud: Decimal
    mid: Decimal | None             # None if book unavailable / stale
    allocation_before_pct: Decimal  # 0-100
    allocation_after_pct: Decimal   # 0-100


@dataclass(frozen=True)
class NotificationContext:
    strategy_name: str
    execution_mode: str             # "llm_agent" | "deterministic"
    strategy_id: str
    confidence: str | None          # "high" | "medium" | "low" | None
    frontend_url: str               # "" → no click URL


def _format_mid(leg: NotificationLeg) -> str:
    if leg.mid is None:
        return ""
    # 4 sig figs is enough — phone screen is small.
    return f" @ ~${leg.mid:.0f} (mid)" if leg.mid >= 100 else f" @ ~${leg.mid:.2f} (mid)"


def _pair_tag(pair: str) -> str:
    return pair.lower().replace("/", "_")


def _format_single_leg(leg: NotificationLeg, ctx: NotificationContext) -> dict:
    base_asset = leg.pair.split("/")[0]
    lines: list[str] = [
        f"{leg.notional_aud:.0f} AUD{_format_mid(leg)}",
        f"{base_asset} allocation after: "
        f"{leg.allocation_after_pct:.0f}% (was {leg.allocation_before_pct:.0f}%)",
    ]
    if ctx.execution_mode == "llm_agent":
        lines.append(f"Confidence: {ctx.confidence or '—'}")
    return {
        "title": f"{leg.side.upper()} {leg.pair} — {ctx.strategy_name}",
        "message": "\n".join(lines),
        "tags": [leg.side, _pair_tag(leg.pair)],
        "click": (
            f"{ctx.frontend_url}/strategies/{ctx.strategy_id}"
            if ctx.frontend_url else ""
        ),
    }


def _format_multi_leg(
    legs: list[NotificationLeg], ctx: NotificationContext,
) -> dict:
    visible = legs[:MAX_VISIBLE_LEGS]
    overflow = len(legs) - len(visible)
    lines: list[str] = []
    for leg in visible:
        base_asset = leg.pair.split("/")[0]
        # Compact line: SIDE ASSET   N AUD @ ~$P
        mid_part = _format_mid(leg).strip()
        lines.append(
            f"{leg.side.upper()} {base_asset:<5} "
            f"{leg.notional_aud:>4.0f} AUD"
            + (f" {mid_part}" if mid_part else "")
        )
    if overflow > 0:
        lines.append(f"… +{overflow} more")
    lines.append(f"Source: {ctx.strategy_name} ({ctx.execution_mode})")
    return {
        "title": f"{ctx.strategy_name} — {len(legs)} orders",
        "message": "\n".join(lines),
        "tags": ["rebalance"],
        "click": (
            f"{ctx.frontend_url}/strategies/{ctx.strategy_id}"
            if ctx.frontend_url else ""
        ),
    }


def render_payload(
    legs: list[NotificationLeg], ctx: NotificationContext,
) -> dict | None:
    """Return an ntfy-publish-shaped dict, or None if there are no legs.

    The caller is expected to add `topic` separately before POSTing.
    """
    if not legs:
        return None
    if len(legs) == 1:
        return _format_single_leg(legs[0], ctx)
    return _format_multi_leg(legs, ctx)
