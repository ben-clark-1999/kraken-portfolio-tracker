from datetime import datetime, timezone

import pytest
from backend.db.supabase_client import get_supabase
from backend.models.up import UpAccount
from backend.repositories import up_accounts_repo
from backend.services import up_snapshot_service

SCHEMA = "test"


@pytest.fixture(autouse=True)
def _truncate():
    db = get_supabase()
    db.schema(SCHEMA).table("portfolio_snapshots").delete().neq(
        "id", "00000000-0000-0000-0000-000000000001"
    ).execute()
    db.schema(SCHEMA).table("up_accounts").delete().neq("id", "").execute()
    yield


def test_save_snapshot_writes_total_balance_with_source_up():
    up_accounts_repo.upsert_many([
        UpAccount(id="a1", display_name="X", account_type="TRANSACTIONAL",
                  ownership_type="INDIVIDUAL", balance_value=100.0,
                  created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        UpAccount(id="a2", display_name="Y", account_type="SAVER",
                  ownership_type="INDIVIDUAL", balance_value=250.50,
                  created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
    ], schema=SCHEMA)

    up_snapshot_service.save_snapshot(schema=SCHEMA)

    rows = (
        get_supabase().schema(SCHEMA).table("portfolio_snapshots")
        .select("*").eq("source", "up").execute().data
    )
    assert len(rows) == 1
    assert float(rows[0]["total_value_aud"]) == 350.50
