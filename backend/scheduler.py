import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.services import portfolio_service, snapshot_service, up_snapshot_service, up_sync_service

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _emit_job_alert(*, code: str, message: str, payload: dict | None = None) -> None:
    """Surface a scheduled-job failure as a system_alert.

    Best-effort: if the alert insert itself fails we just log — the
    exception that triggered this is already in the log.
    """
    try:
        from backend.repositories import system_alerts_repo as alerts
        alerts.insert(
            level="warning", code=code, strategy_id=None,
            message=message, payload=payload or {},
        )
    except Exception:
        logger.exception("Failed to insert system_alert for %s", code)


def _do_snapshot() -> None:
    """Synchronous snapshot composition for both crypto and UP."""
    summary = portfolio_service.build_summary()
    snapshot_service.save_snapshot(summary)
    try:
        up_snapshot_service.save_snapshot()
    except Exception as exc:
        logger.exception("UP snapshot failed (crypto snapshot was saved)")
        _emit_job_alert(
            code="UP_SNAPSHOT_FAILED",
            message=f"UP snapshot failed: {exc!r}",
            payload={"exception": str(exc)},
        )


async def _hourly_snapshot() -> None:
    try:
        await asyncio.to_thread(_do_snapshot)
    except Exception as exc:
        logger.exception("Hourly snapshot failed")
        _emit_job_alert(
            code="HOURLY_SNAPSHOT_FAILED",
            message=f"Hourly snapshot failed: {exc!r}",
            payload={"exception": str(exc)},
        )


async def _up_sync_tick() -> None:
    try:
        await up_sync_service.sync()
    except Exception as exc:
        logger.exception("UP sync tick failed")
        _emit_job_alert(
            code="UP_SYNC_FAILED",
            message=f"UP sync tick failed: {exc!r}",
            payload={"exception": str(exc)},
        )


def start_scheduler() -> None:
    scheduler.add_job(_hourly_snapshot, "interval", hours=1, id="hourly_snapshot")
    # IntervalTrigger schedules the first run at start_date + interval (i.e.,
    # ~15 min from now). Don't pass next_run_time=None here — that adds the
    # job in a paused state and the interval never fires. The immediate kick
    # below handles the boot-time backfill so we don't wait 15 min for it.
    scheduler.add_job(_up_sync_tick, "interval", minutes=15, id="up_sync")
    scheduler.start()
    asyncio.get_event_loop().create_task(_up_sync_tick())


def stop_scheduler() -> None:
    scheduler.shutdown()


def register_all_strategy_triggers() -> None:
    """Called from main.py on startup after the schedulers are running."""
    from backend.repositories import strategies_repo
    from backend.services.trading.trigger_scheduler import register_strategy_triggers

    for strat in strategies_repo.list_active():
        register_strategy_triggers(strat, scheduler=scheduler)
