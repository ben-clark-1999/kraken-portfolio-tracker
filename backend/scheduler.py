import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.services import portfolio_service, snapshot_service, up_snapshot_service, up_sync_service

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _do_snapshot() -> None:
    """Synchronous snapshot composition for both crypto and UP."""
    summary = portfolio_service.build_summary()
    snapshot_service.save_snapshot(summary)
    try:
        up_snapshot_service.save_snapshot()
    except Exception:
        logger.exception("UP snapshot failed (crypto snapshot was saved)")


async def _hourly_snapshot() -> None:
    try:
        await asyncio.to_thread(_do_snapshot)
    except Exception:
        logger.exception("Hourly snapshot failed")


async def _up_sync_tick() -> None:
    try:
        await up_sync_service.sync()
    except Exception:
        logger.exception("UP sync tick failed")


def start_scheduler() -> None:
    scheduler.add_job(_hourly_snapshot, "interval", hours=1, id="hourly_snapshot")
    scheduler.add_job(_up_sync_tick, "interval", minutes=15, id="up_sync", next_run_time=None)
    scheduler.start()
    # Kick off first UP sync immediately (in background) so first-run backfill starts
    asyncio.get_event_loop().create_task(_up_sync_tick())


def stop_scheduler() -> None:
    scheduler.shutdown()
