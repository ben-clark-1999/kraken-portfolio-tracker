"""Data access for `up_accounts`."""

from datetime import datetime, timezone

from backend.db.supabase_client import get_supabase
from backend.models.up import UpAccount


def upsert_many(accounts: list[UpAccount], schema: str = "public") -> None:
    if not accounts:
        return
    db = get_supabase()
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = [{
        "id": a.id,
        "display_name": a.display_name,
        "account_type": a.account_type,
        "ownership_type": a.ownership_type,
        "balance_value": a.balance_value,
        "balance_currency": a.balance_currency,
        "created_at": a.created_at.isoformat(),
        "last_synced_at": now_iso,
    } for a in accounts]
    db.schema(schema).table("up_accounts").upsert(rows).execute()


def list_all(schema: str = "public") -> list[UpAccount]:
    db = get_supabase()
    result = db.schema(schema).table("up_accounts").select("*").execute()
    out: list[UpAccount] = []
    for row in result.data:
        out.append(UpAccount(
            id=row["id"],
            display_name=row["display_name"],
            account_type=row["account_type"],
            ownership_type=row["ownership_type"],
            balance_value=float(row["balance_value"]),
            balance_currency=row["balance_currency"],
            created_at=row["created_at"],
        ))
    return out


def total_balance(schema: str = "public") -> float:
    return sum(a.balance_value for a in list_all(schema=schema))
