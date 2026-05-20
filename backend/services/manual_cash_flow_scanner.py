"""Debounced scanner that pulls Kraken deposit/withdrawal entries into
manual_cash_flows. Runs from the leaderboard router; no scheduler job.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from backend.repositories import manual_cash_flows_repo, system_alerts_repo
from backend.services import kraken_service

logger = logging.getLogger(__name__)

_DEBOUNCE_SECONDS = 300   # 5 minutes


def ensure_cash_flows_fresh(*, schema: str = "public") -> None:
    """Pull new Kraken cash-flow entries and persist them.

    Idempotent. Debounced — skipped if last_created_at is within
    _DEBOUNCE_SECONDS. Best-effort — never raises into the caller.
    """
    try:
        last_scanned = manual_cash_flows_repo.last_created_at(schema=schema)
        now = datetime.now(timezone.utc)
        if last_scanned is not None and (now - last_scanned).total_seconds() < _DEBOUNCE_SECONDS:
            return

        since = manual_cash_flows_repo.latest_occurred_at(schema=schema)
        entries = kraken_service.get_cash_flow_entries(since=since)

        for entry in entries:
            if entry["asset"] != "AUD":
                try:
                    system_alerts_repo.insert(
                        level="warning",
                        code="MANUAL_CASHFLOW_NON_AUD",
                        strategy_id=None,
                        message=(
                            f"Non-AUD cash flow detected on Kraken: "
                            f"{entry['asset']} {entry['amount_aud']}"
                        ),
                        payload={
                            "refid": entry["kraken_refid"],
                            "asset": entry["asset"],
                            "amount": str(entry["amount_aud"]),
                            "kind": entry["kind"],
                        },
                        schema=schema,
                    )
                except Exception:
                    logger.exception("Failed to insert MANUAL_CASHFLOW_NON_AUD alert")
                continue

            manual_cash_flows_repo.upsert_by_refid(
                kraken_refid=entry["kraken_refid"],
                kind=entry["kind"],
                amount_aud=entry["amount_aud"],
                occurred_at=entry["occurred_at"],
                schema=schema,
            )
    except Exception:
        logger.exception("ensure_cash_flows_fresh failed; leaderboard will use stale data")
