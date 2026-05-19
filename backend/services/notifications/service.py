"""Notification orchestration: assemble payload, POST to ntfy, mark notified.

Best-effort: failures emit a system_alert but never raise into the
caller (write_agent_decision). Designed so the trading loop is never
blocked by a phone-broker outage.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable
from uuid import UUID

import httpx

from backend.repositories import (
    agent_decisions_repo, paper_positions_repo, strategies_repo,
    system_alerts_repo,
)
from backend.services.notifications.payload import (
    NotificationContext, NotificationLeg, render_payload,
)

logger = logging.getLogger(__name__)

_CONFIDENCE_RE = re.compile(
    r"<confidence>\s*(high|medium|low)\s*</confidence>", re.IGNORECASE
)
_PLACE_PAPER_ORDER = "place_paper_order"
_REQUEST_TIMEOUT_S = 5.0
_RETRY_BACKOFF_S = 1.0


def _extract_confidence(agent_output: str | None) -> str | None:
    if not agent_output:
        return None
    match = _CONFIDENCE_RE.search(agent_output)
    return match.group(1).lower() if match else None


def _filter_legs(tool_calls: Iterable[dict]) -> list[dict]:
    legs: list[dict] = []
    for c in tool_calls or []:
        if c.get("tool") != _PLACE_PAPER_ORDER:
            continue
        args = c.get("args") or {}
        side = args.get("side")
        if side not in ("buy", "sell"):
            continue
        legs.append(args)
    return legs


def _resolve_mid(books: dict, pair: str) -> Decimal | None:
    book = books.get(pair) if books else None
    if book is None:
        return None
    # Match the freshness gate used in the executor's market path.
    try:
        if not book.bids or not book.asks:
            return None
        if book.age_seconds(datetime.now(timezone.utc)) > 5:
            return None
        return book.mid()
    except Exception:
        return None


def _build_leg(
    args: dict, *, current_positions: dict, total_notional_aud: Decimal,
    books: dict,
) -> NotificationLeg:
    pair = args["pair"]
    side = args["side"]
    notional = Decimal(str(args["notional_aud"]))
    mid = _resolve_mid(books, pair)
    base_asset = pair.split("/")[0]
    asset_qty = Decimal(str(current_positions.get(base_asset, {}).get("qty", "0")))
    avg_cost = Decimal(str(current_positions.get(base_asset, {}).get("avg_cost_aud", "0")))
    before_aud = asset_qty * (mid or avg_cost)
    delta = notional if side == "buy" else -notional
    after_aud = before_aud + delta
    new_total = total_notional_aud + (delta if side == "buy" else Decimal("0"))

    def _pct(n: Decimal, d: Decimal) -> Decimal:
        return (n / d * Decimal("100")) if d > 0 else Decimal("0")

    return NotificationLeg(
        side=side, pair=pair, notional_aud=notional, mid=mid,
        allocation_before_pct=_pct(before_aud, total_notional_aud),
        allocation_after_pct=_pct(after_aud, new_total or total_notional_aud),
    )


async def _post_with_retry(
    *, url: str, json_body: dict, decision_id: str, schema: str,
) -> None:
    last_err: str | None = None
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_S) as client:
        for attempts in (1, 2):
            try:
                r = await client.post(url, json=json_body)
                if 200 <= r.status_code < 300:
                    return
                last_err = f"HTTP {r.status_code}: {r.text[:200]}"
            except Exception as exc:
                last_err = repr(exc)
            if attempts == 1:
                await asyncio.sleep(_RETRY_BACKOFF_S)
    # Both attempts failed.
    try:
        system_alerts_repo.insert(
            level="warning", code="PUSH_NOTIFY_FAILED",
            strategy_id=None,
            message="Push notification failed after retry",
            payload={"decision_id": decision_id, "error": last_err or "unknown"},
            schema=schema,
        )
    except Exception:
        logger.exception("Failed to insert PUSH_NOTIFY_FAILED alert")


async def maybe_notify(
    *,
    decision_id: str,
    strategy_id: UUID | str,
    tool_calls: list[dict] | None,
    agent_output: str | None,
    schema: str = "public",
    books: dict | None = None,
    ntfy_topic: str | None = None,
    ntfy_url_base: str | None = None,
    frontend_url: str | None = None,
) -> None:
    """Send one ntfy notification for `decision_id` if eligible.

    Eligibility (all must hold):
    - `ntfy_topic` resolves to a non-empty string.
    - The strategy has `notify_enabled = True`.
    - `tool_calls` contains at least one `place_paper_order` with a
       buy/sell side.
    - The decision has `notified_at IS NULL` (idempotency guard).

    All arguments after `decision_id` are passed in by the caller so
    this function stays trivially testable; defaults are resolved
    against `backend.config.settings` when None.
    """
    try:
        from backend.config import settings as _settings
        topic = ntfy_topic if ntfy_topic is not None else _settings.ntfy_topic
        url_base = ntfy_url_base if ntfy_url_base is not None else _settings.ntfy_url_base
        fe_url = frontend_url if frontend_url is not None else _settings.frontend_url

        if not topic:
            return

        legs_args = _filter_legs(tool_calls or [])
        if not legs_args:
            return

        strat = strategies_repo.get(UUID(str(strategy_id)), schema=schema)
        if strat is None or not strat.notify_enabled:
            return

        # Resolve books from caller, or fall back to the executor singleton.
        if books is None:
            from backend.services.trading import strategy_loop
            ex = getattr(strategy_loop, "_current_executor", None)
            books = (getattr(ex, "_books", {}) if ex is not None else {}) or {}

        positions = paper_positions_repo.get_all(
            UUID(str(strategy_id)), schema=schema,
        )
        # Total notional ≈ sum(qty * mid_or_avg) over non-AUD + AUD cash.
        total = Decimal("0")
        for asset, row in positions.items():
            qty = Decimal(str(row.get("qty", "0")))
            if asset == "AUD":
                total += qty
                continue
            pair = f"{asset}/AUD"
            mid = _resolve_mid(books, pair) or Decimal(str(row.get("avg_cost_aud", "0")))
            total += qty * mid

        legs = [
            _build_leg(a, current_positions=positions,
                       total_notional_aud=total, books=books)
            for a in legs_args
        ]

        ctx = NotificationContext(
            strategy_name=strat.name,
            execution_mode=strat.execution_mode,
            strategy_id=str(strategy_id),
            confidence=_extract_confidence(agent_output),
            frontend_url=fe_url or "",
        )
        payload = render_payload(legs, ctx)
        if payload is None:
            return

        # Atomic-ish: only POST if we successfully claim the decision.
        if not agent_decisions_repo.mark_notified(decision_id, schema=schema):
            return

        url = f"{url_base.rstrip('/')}/{topic}"
        await _post_with_retry(
            url=url, json_body=payload,
            decision_id=decision_id, schema=schema,
        )
    except Exception as exc:
        logger.exception("maybe_notify failed unexpectedly")
        try:
            system_alerts_repo.insert(
                level="warning", code="PUSH_NOTIFY_FAILED",
                strategy_id=None,
                message=f"maybe_notify raised: {exc!r}",
                payload={"decision_id": decision_id, "error": repr(exc)},
                schema=schema,
            )
        except Exception:
            logger.exception("Also failed to insert outer-catch system_alert")
