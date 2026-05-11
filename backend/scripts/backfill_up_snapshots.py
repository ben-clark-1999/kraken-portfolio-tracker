"""One-shot backfill of historical UP balance snapshots from transactions.

Walks the transaction log backwards from the current account balance to
compute a daily balance series, then inserts one `portfolio_snapshots` row
per day with `source='up'` at midnight UTC.

The math:
    balance(T) = current_balance - sum(amount_value where created_at > T)

Idempotent: skips days that already have a UP snapshot at midnight UTC.

Usage:
    cd /path/to/repo
    backend/.venv/bin/python -m backend.scripts.backfill_up_snapshots
"""

import logging
from datetime import datetime, timedelta, timezone

from backend.db.supabase_client import get_supabase
from backend.repositories import snapshots_repo, up_accounts_repo

SCHEMA = "public"

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    accounts = up_accounts_repo.list_all(schema=SCHEMA)
    if not accounts:
        logger.info("No UP accounts loaded — run a sync first.")
        return
    current_balance = sum(a.balance_value for a in accounts)
    logger.info(
        "Current UP balance: $%.2f across %d accounts",
        current_balance, len(accounts),
    )

    db = get_supabase()
    tx_rows = (
        db.schema(SCHEMA).table("up_transactions")
        .select("created_at,amount_value")
        .order("created_at", desc=True)
        .execute().data
    )
    if not tx_rows:
        logger.info("No transactions — nothing to backfill.")
        return

    txs = [
        (datetime.fromisoformat(r["created_at"]), float(r["amount_value"]))
        for r in tx_rows
    ]
    earliest_tx = min(t[0] for t in txs)
    logger.info(
        "Found %d transactions, earliest %s", len(txs), earliest_tx.isoformat(),
    )

    today_midnight = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )
    earliest_day = earliest_tx.astimezone(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )

    existing = {
        r["captured_at"]
        for r in snapshots_repo.list_by_source(source="up", schema=SCHEMA)
    }

    inserted = 0
    skipped = 0
    day = today_midnight
    while day >= earliest_day:
        midnight_iso = day.isoformat()
        if midnight_iso in existing:
            skipped += 1
        else:
            future_amount = sum(amount for (dt, amount) in txs if dt > day)
            balance = current_balance - future_amount
            snapshots_repo.insert_source_snapshot(
                captured_at=midnight_iso,
                total_value_aud=round(balance, 2),
                source="up",
                schema=SCHEMA,
            )
            inserted += 1
        day -= timedelta(days=1)

    logger.info(
        "Backfill complete — %d inserted, %d skipped (already existed)",
        inserted, skipped,
    )


if __name__ == "__main__":
    main()
