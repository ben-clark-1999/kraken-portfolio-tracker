from fastapi import APIRouter, HTTPException
from backend.services import kraken_service
from backend.services.sync_service import (
    get_last_synced_trade_id,
    upsert_lots,
    record_sync,
)

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
        record_sync(last_trade_id=None, status="error", error_message=str(e))
        raise HTTPException(status_code=502, detail=str(e))
