import logging

from fastapi import APIRouter

from backend.services import kraken_service
from backend.services.sync_service import (
    get_last_synced_trade_id,
    upsert_lots,
    record_sync,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("")
async def trigger_sync() -> dict:
    last_trade_id = get_last_synced_trade_id()
    try:
        trades = kraken_service.get_trade_history(since_trade_id=last_trade_id)
        new_last_id = upsert_lots(trades)
        record_sync(last_trade_id=new_last_id or last_trade_id, status="success")
        return {"synced": len(trades), "last_trade_id": new_last_id}
    except Exception:
        # Persist failure in sync_log for the dashboard's audit trail, then
        # let the global handler return the sanitized 5xx.
        try:
            record_sync(
                last_trade_id=None,
                status="error",
                error_message="sync failed (see server logs)",
            )
        except Exception:
            logger.exception("Failed to record sync error row")
        raise
