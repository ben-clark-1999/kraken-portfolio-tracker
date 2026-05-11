"""Data access for `up_transactions`."""

from collections import defaultdict
from datetime import datetime

from backend.db.supabase_client import get_supabase
from backend.models.up import UpTransaction


def upsert_many(txs: list[UpTransaction], schema: str = "public") -> None:
    if not txs:
        return
    db = get_supabase()
    rows = [{
        "id": t.id,
        "account_id": t.account_id,
        "status": t.status,
        "description": t.description,
        "message": t.message,
        "raw_text": t.raw_text,
        "amount_value": t.amount_value,
        "amount_currency": t.amount_currency,
        "category_id": t.category_id,
        "parent_category_id": t.parent_category_id,
        "created_at": t.created_at.isoformat(),
        "settled_at": t.settled_at.isoformat() if t.settled_at else None,
    } for t in txs]
    db.schema(schema).table("up_transactions").upsert(rows).execute()


def _row_to_tx(row: dict) -> UpTransaction:
    return UpTransaction(
        id=row["id"], account_id=row["account_id"], status=row["status"],
        description=row["description"], message=row.get("message"), raw_text=row.get("raw_text"),
        amount_value=float(row["amount_value"]), amount_currency=row["amount_currency"],
        category_id=row.get("category_id"), parent_category_id=row.get("parent_category_id"),
        created_at=row["created_at"],
        settled_at=row.get("settled_at"),
    )


def list_recent(
    *, limit: int = 50, since: datetime | None = None, schema: str = "public",
) -> list[UpTransaction]:
    db = get_supabase()
    q = db.schema(schema).table("up_transactions").select("*").order("created_at", desc=True).limit(limit)
    if since:
        q = q.gte("created_at", since.isoformat())
    return [_row_to_tx(r) for r in q.execute().data]


def max_created_at(schema: str = "public") -> datetime | None:
    db = get_supabase()
    result = (
        db.schema(schema).table("up_transactions")
        .select("created_at").order("created_at", desc=True).limit(1).execute()
    )
    if not result.data:
        return None
    return datetime.fromisoformat(result.data[0]["created_at"])


def spending_by_parent_category(
    *, since: datetime, until: datetime, schema: str = "public",
) -> dict[str, float]:
    """Sum of |amount| for negative-amount transactions per parent category."""
    db = get_supabase()
    result = (
        db.schema(schema).table("up_transactions")
        .select("parent_category_id,amount_value")
        .gte("created_at", since.isoformat())
        .lte("created_at", until.isoformat())
        .lt("amount_value", 0)
        .execute()
    )
    out: dict[str, float] = defaultdict(float)
    for row in result.data:
        cat = row.get("parent_category_id") or "uncategorised"
        out[cat] += abs(float(row["amount_value"]))
    return dict(out)


def cashflow_by_period(
    *, since: datetime, until: datetime, granularity: str = "month", schema: str = "public",
) -> list[dict]:
    """List of {period, income, expense} from `since` to `until`.

    Bucketed in Python (not SQL) so we don't depend on Postgres date_trunc
    via supabase-py — keeps the repo backend-agnostic.
    """
    rows = list_recent(limit=10_000, since=since, schema=schema)
    rows = [r for r in rows if r.created_at <= until]
    buckets: dict[str, dict[str, float]] = defaultdict(lambda: {"income": 0.0, "expense": 0.0})
    for r in rows:
        key = _bucket_key(r.created_at, granularity)
        if r.amount_value >= 0:
            buckets[key]["income"] += r.amount_value
        else:
            buckets[key]["expense"] += abs(r.amount_value)
    return [
        {"period": k, "income": round(v["income"], 2), "expense": round(v["expense"], 2)}
        for k, v in sorted(buckets.items())
    ]


def _bucket_key(dt: datetime, granularity: str) -> str:
    if granularity == "day":
        return dt.date().isoformat()
    if granularity == "week":
        iso = dt.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    return f"{dt.year:04d}-{dt.month:02d}"  # month
