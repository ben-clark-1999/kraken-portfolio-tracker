import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from backend.services import kraken_service, portfolio_service, snapshot_service
from backend.services.sync_service import get_all_lots

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def _hourly_snapshot() -> None:
    try:
        balances = kraken_service.get_balances()
        prices = kraken_service.get_ticker_prices(list(balances.keys()))
        lots = get_all_lots()
        summary = portfolio_service.calculate_summary(balances, prices, lots)
        snapshot_service.save_snapshot(summary)
    except Exception:
        # Log but don't crash the scheduler
        logger.exception("Hourly snapshot failed")


def start_scheduler() -> None:
    scheduler.add_job(_hourly_snapshot, "interval", hours=1, id="hourly_snapshot")
    scheduler.start()


def stop_scheduler() -> None:
    scheduler.shutdown()
