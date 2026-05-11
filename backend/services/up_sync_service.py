"""Orchestrates UP Bank sync: first-run backfill + incremental updates."""

import logging
from datetime import datetime, timedelta

from backend.config import settings
from backend.repositories import (
    up_accounts_repo, up_categories_repo, up_sync_log_repo, up_transactions_repo,
)
from backend.services.up_client import UpClient

logger = logging.getLogger(__name__)

OVERLAP = timedelta(hours=6)


def _make_client() -> UpClient:
    return UpClient(settings.up_pat)


async def sync(*, client: UpClient | None = None, schema: str = "public") -> None:
    """Run a sync cycle. First run backfills all-time; subsequent runs are
    incremental with an overlap window that catches HELD→SETTLED."""
    client = client or _make_client()
    sync_id = up_sync_log_repo.record_start(schema=schema)
    last_seen_prior = up_sync_log_repo.last_successful_seen_tx_at(schema=schema)

    try:
        accounts = await client.list_accounts()
        up_accounts_repo.upsert_many(accounts, schema=schema)

        if last_seen_prior is None:
            categories = await client.list_categories()
            up_categories_repo.upsert_many(categories, schema=schema)
            since = None
            logger.info("[UpSync] First run — full backfill")
        else:
            since = last_seen_prior - OVERLAP
            logger.info("[UpSync] Incremental — since=%s", since.isoformat())

        max_seen = last_seen_prior
        batch: list = []
        async for tx in client.list_transactions(since=since):
            batch.append(tx)
            if len(batch) >= 100:
                up_transactions_repo.upsert_many(batch, schema=schema)
                batch = []
            if max_seen is None or tx.created_at > max_seen:
                max_seen = tx.created_at
        if batch:
            up_transactions_repo.upsert_many(batch, schema=schema)

        up_sync_log_repo.finalize_success(sync_id, last_seen_tx_at=max_seen, schema=schema)
        logger.info("[UpSync] Success — last_seen_tx_at=%s", max_seen)
    except Exception as exc:
        up_sync_log_repo.finalize_error(sync_id, error_message=str(exc), schema=schema)
        logger.exception("[UpSync] Failed")
        raise
