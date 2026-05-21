"""Debounced scanner that pulls Kraken deposit/withdrawal entries and spot
trades into manual_cash_flows + manual_trades. Runs from the leaderboard
router; no scheduler job.

Persisting trades lets the leaderboard build the Manual row from durable
DB state instead of a live Kraken call — Kraken REST hiccups otherwise
make the row read as "$0, 0 trades" when the user actually has activity.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal

from backend.config.assets import LEDGER_ASSET_TO_DISPLAY
from backend.repositories import (
    manual_cash_flows_repo, manual_trades_repo, system_alerts_repo,
)
from backend.services import kraken_service

logger = logging.getLogger(__name__)

_DEBOUNCE_SECONDS = 300   # 5 minutes


def ensure_cash_flows_fresh(*, schema: str = "public") -> None:
    """Pull new Kraken cash-flow + trade entries and persist them.

    Idempotent. Debounced — skipped if last_created_at is within
    _DEBOUNCE_SECONDS. Best-effort — never raises into the caller.
    """
    try:
        last_scanned = manual_cash_flows_repo.last_created_at(schema=schema)
        now = datetime.now(timezone.utc)
        if last_scanned is not None and (now - last_scanned).total_seconds() < _DEBOUNCE_SECONDS:
            return

        # Cash flows from the deposit/withdrawal-only helper (existing path).
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

        # Trades: walk the full ledger once and pair spend/receive entries
        # by refid. Persisting these means the leaderboard endpoint can
        # render Manual from DB even if Kraken REST is unreachable.
        _persist_trades_from_ledger(schema=schema)

    except Exception:
        logger.exception("ensure_cash_flows_fresh failed; leaderboard will use stale data")


def _persist_trades_from_ledger(*, schema: str) -> None:
    """Group ledger entries by refid; emit a manual_trades row per spot trade.

    A Kraken spot trade is two ledger entries sharing a refid: a `spend`
    of ZAUD (-AUD) plus a `receive` of the crypto for buys, or a `spend`
    of crypto plus a `receive` of ZAUD (+AUD) for sells. Staking, fees,
    and transfers don't share that pattern and are filtered out.
    """
    try:
        ledger = kraken_service.get_all_ledger_entries()
    except Exception:
        logger.exception("manual_trades: failed to fetch Kraken ledger; skipping trade persist")
        return

    by_refid: dict[str, list[dict]] = {}
    for e in ledger:
        rid = e.get("refid")
        if not rid:
            continue
        by_refid.setdefault(rid, []).append(e)

    for rid, entries in by_refid.items():
        if len(entries) < 2:
            continue
        aud = next(
            (x for x in entries
             if x.get("asset") == "ZAUD" and x.get("type") in ("spend", "receive")),
            None,
        )
        crypto = next(
            (x for x in entries
             if x.get("asset") != "ZAUD"
             and x.get("type") in ("receive", "spend")
             and LEDGER_ASSET_TO_DISPLAY.get(x.get("asset", ""))),
            None,
        )
        if aud is None or crypto is None:
            continue

        aud_amount = Decimal(str(aud["amount"]))
        crypto_amount = Decimal(str(crypto["amount"]))
        if aud["type"] == "spend" and crypto["type"] == "receive":
            side = "buy"
        elif aud["type"] == "receive" and crypto["type"] == "spend":
            side = "sell"
        else:
            continue

        try:
            fee = Decimal(str(aud.get("fee") or 0))
        except Exception:
            fee = Decimal("0")

        manual_trades_repo.upsert_by_refid(
            kraken_refid=rid,
            side=side,
            base_asset=LEDGER_ASSET_TO_DISPLAY[crypto["asset"]],
            base_qty=abs(crypto_amount),
            aud_amount=abs(aud_amount),
            fee_aud=fee,
            occurred_at=datetime.fromtimestamp(float(aud["time"]), tz=timezone.utc),
            schema=schema,
        )
