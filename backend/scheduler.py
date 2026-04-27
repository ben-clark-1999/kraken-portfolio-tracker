import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.services import portfolio_service, snapshot_service, storage_service

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _do_snapshot() -> None:
    """Synchronous snapshot composition. Kept separate from the scheduled
    coroutine so it can be offloaded to a worker thread."""
    summary = portfolio_service.build_summary()
    snapshot_service.save_snapshot(summary)


async def _hourly_snapshot() -> None:
    """Hourly snapshot job.

    The work itself is synchronous (kraken-sdk and supabase-py are blocking
    I/O). AsyncIOScheduler runs async jobs directly on the FastAPI event
    loop, so we offload to a worker thread via asyncio.to_thread to avoid
    stalling request handling for the ~5-10s a snapshot takes.
    """
    try:
        await asyncio.to_thread(_do_snapshot)
    except Exception:
        # Log but don't crash the scheduler
        logger.exception("Hourly snapshot failed")


def _do_pending_sweep() -> None:
    """Synchronous pending-attachment sweep."""
    swept = storage_service.sweep_pending_attachments(older_than_hours=24)
    if swept > 0:
        logger.info("Pending-attachment sweep removed %d orphans", swept)


async def _pending_sweep_job() -> None:
    """6-hourly sweep for orphan tax attachments."""
    try:
        await asyncio.to_thread(_do_pending_sweep)
    except Exception:
        logger.exception("Pending-attachment sweep failed")


def start_scheduler() -> None:
    scheduler.add_job(_hourly_snapshot, "interval", hours=1, id="hourly_snapshot")
    scheduler.add_job(
        _pending_sweep_job,
        "interval",
        hours=6,
        id="pending_sweep",
    )
    scheduler.start()


def stop_scheduler() -> None:
    scheduler.shutdown()
