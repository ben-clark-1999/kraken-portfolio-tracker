"""REST endpoints for UP Bank data."""

from fastapi import APIRouter, Depends

from backend.auth.dependencies import require_auth
from backend.repositories import up_accounts_repo

router = APIRouter(prefix="/api/up", tags=["up"], dependencies=[Depends(require_auth)])

SCHEMA = "public"


@router.get("/accounts")
async def list_accounts() -> list[dict]:
    accounts = up_accounts_repo.list_all(schema=SCHEMA)
    return [a.model_dump(mode="json") for a in accounts]
