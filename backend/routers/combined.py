"""Combined view across crypto + UP."""

from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends

from backend.auth.dependencies import require_auth
from backend.repositories import snapshots_repo

router = APIRouter(prefix="/api/combined", tags=["combined"], dependencies=[Depends(require_auth)])

SCHEMA = "public"


def _hour_bucket(iso_ts: str) -> str:
    """Round a captured_at timestamp down to the hour, in UTC.

    Crypto and UP snapshots are written by the same scheduler tick but call
    `datetime.now()` independently, landing milliseconds apart. Bucketing
    by hour ensures both sources merge into one row in the chart.
    """
    dt = datetime.fromisoformat(iso_ts)
    return dt.replace(minute=0, second=0, microsecond=0).isoformat()


@router.get("/snapshots")
async def snapshots(since: str | None = None) -> list[dict]:
    rows = snapshots_repo.list_by_source(since=since, schema=SCHEMA)
    by_ts: dict[str, dict[str, float]] = defaultdict(lambda: {"crypto": 0.0, "up": 0.0})
    for r in rows:
        bucket = _hour_bucket(r["captured_at"])
        by_ts[bucket][r["source"]] += float(r["total_value_aud"])
    out: list[dict] = []
    for ts in sorted(by_ts.keys()):
        crypto = by_ts[ts]["crypto"]
        up = by_ts[ts]["up"]
        out.append({"captured_at": ts, "crypto": crypto, "up": up, "total": crypto + up})
    return out


@router.get("/summary")
async def summary() -> dict:
    rows = snapshots_repo.list_by_source(schema=SCHEMA)
    latest_by_source: dict[str, float] = {}
    for r in rows:
        # rows are ordered ascending by captured_at; later overwrites earlier
        latest_by_source[r["source"]] = float(r["total_value_aud"])
    crypto = latest_by_source.get("crypto", 0.0)
    up = latest_by_source.get("up", 0.0)
    return {"crypto": crypto, "up": up, "total": crypto + up}
