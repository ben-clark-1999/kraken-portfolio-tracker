"""Thin wrapper around agent_decisions_repo for the strategy loop.

Also the seam where push notifications fan out on a freshly inserted
decision (spec: docs/superpowers/specs/2026-05-19-push-notifications-design.md).
The fan-out is best-effort and runs as a fire-and-forget task so the
caller never waits on the phone broker.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from backend.repositories.agent_decisions_repo import insert as _insert

logger = logging.getLogger(__name__)


def write_agent_decision(
    *, _notify_overrides: dict[str, Any] | None = None, **kwargs,
) -> str:
    decision_id = _insert(**kwargs)
    _schedule_notify(decision_id, kwargs, _notify_overrides)
    return decision_id


def _schedule_notify(
    decision_id: str,
    kwargs: dict[str, Any],
    overrides: dict[str, Any] | None,
) -> None:
    """Fire-and-forget notification. Never raises."""
    try:
        from backend.services.notifications import maybe_notify
    except Exception:
        logger.exception("Notification import failed; skipping")
        return

    overrides = overrides or {}
    coro = maybe_notify(
        decision_id=decision_id,
        strategy_id=kwargs.get("strategy_id"),
        tool_calls=kwargs.get("tool_calls") or [],
        agent_output=kwargs.get("agent_output"),
        schema=kwargs.get("schema", "public"),
        ntfy_topic=overrides.get("ntfy_topic"),
        ntfy_url_base=overrides.get("ntfy_url_base"),
        frontend_url=overrides.get("frontend_url"),
    )

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        # No running loop — caller is a sync test or boot path.
        # Run to completion synchronously rather than dropping the task.
        try:
            asyncio.run(coro)
        except Exception:
            logger.exception("Notify failed in sync path")
