"""REST endpoints for UP Bank data."""

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from backend.auth.dependencies import require_auth
from backend.repositories import up_accounts_repo, up_sync_log_repo, up_transactions_repo
from backend.services import up_recurring_service, up_sync_service

router = APIRouter(prefix="/api/up", tags=["up"], dependencies=[Depends(require_auth)])

SCHEMA = "public"


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


@router.get("/accounts")
async def list_accounts() -> list[dict]:
    accounts = up_accounts_repo.list_all(schema=SCHEMA)
    return [a.model_dump(mode="json") for a in accounts]


@router.get("/transactions")
async def list_transactions(
    limit: int = Query(50, ge=1, le=500),
    since: str | None = None,
    until: str | None = None,
) -> list[dict]:
    since_dt = _parse_iso(since) if since else None
    txs = up_transactions_repo.list_recent(limit=limit, since=since_dt, schema=SCHEMA)
    if until:
        until_dt = _parse_iso(until)
        txs = [t for t in txs if t.created_at <= until_dt]
    return [t.model_dump(mode="json") for t in txs]


@router.get("/spending/summary")
async def spending_summary(since: str, until: str) -> dict[str, float]:
    return up_transactions_repo.spending_by_parent_category(
        since=_parse_iso(since),
        until=_parse_iso(until),
        schema=SCHEMA,
    )


@router.get("/cashflow")
async def cashflow(since: str, until: str, granularity: str = "month") -> list[dict]:
    return up_transactions_repo.cashflow_by_period(
        since=_parse_iso(since),
        until=_parse_iso(until),
        granularity=granularity,
        schema=SCHEMA,
    )


_STATE_MAP = {"in_progress": "syncing", "success": "ready", "error": "error"}


@router.get("/sync/status")
async def sync_status() -> dict:
    latest = up_sync_log_repo.latest(schema=SCHEMA)
    if latest is None:
        return {"state": "ready", "last_synced_at": None, "error": None}
    return {
        "state": _STATE_MAP.get(latest["status"], "ready"),
        "last_synced_at": latest.get("synced_at"),
        "error": latest.get("error_message"),
    }


@router.post("/sync/retry", status_code=status.HTTP_202_ACCEPTED)
async def sync_retry(background: BackgroundTasks) -> dict:
    background.add_task(up_sync_service.sync)
    return {"queued": True}


@router.get("/recurring")
async def list_recurring() -> list[dict]:
    charges = up_recurring_service.find_recurring(schema=SCHEMA)
    return [c.model_dump(mode="json") for c in charges]
