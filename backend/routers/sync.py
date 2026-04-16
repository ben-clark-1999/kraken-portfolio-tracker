import logging

from fastapi import APIRouter, HTTPException

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
    try:
        last_trade_id = get_last_synced_trade_id()
        trades = kraken_service.get_trade_history(since_trade_id=last_trade_id)
        new_last_id = upsert_lots(trades)
        record_sync(last_trade_id=new_last_id or last_trade_id, status="success")
        return {"synced": len(trades), "last_trade_id": new_last_id}
    except Exception as e:
        # Preserve the real stack trace; record_sync only persists str(e).
        logger.exception("Sync failed")
        try:
            record_sync(last_trade_id=None, status="error", error_message=str(e))
        except Exception:
            # Don't let a sync_log write failure mask the original error.
            logger.exception("Failed to record sync error row")
        raise HTTPException(status_code=502, detail=str(e))
