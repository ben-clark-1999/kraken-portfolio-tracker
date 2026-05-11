from datetime import datetime, timezone

import pytest
from backend.db.supabase_client import get_supabase
from backend.models.up import UpAccount
from backend.repositories import up_accounts_repo

SCHEMA = "test"


@pytest.fixture(autouse=True)
def _truncate():
    db = get_supabase()
    db.schema(SCHEMA).table("up_transactions").delete().neq("id", "").execute()
    db.schema(SCHEMA).table("up_accounts").delete().neq("id", "").execute()
    yield


def _acct(id: str = "a1", balance: float = 100.0) -> UpAccount:
    return UpAccount(
        id=id, display_name="Spending", account_type="TRANSACTIONAL",
        ownership_type="INDIVIDUAL", balance_value=balance,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_upsert_and_list():
    up_accounts_repo.upsert_many([_acct("a1", 100), _acct("a2", 200)], schema=SCHEMA)
    rows = up_accounts_repo.list_all(schema=SCHEMA)
    assert {r.id for r in rows} == {"a1", "a2"}


def test_upsert_updates_balance():
    up_accounts_repo.upsert_many([_acct("a1", 100)], schema=SCHEMA)
    up_accounts_repo.upsert_many([_acct("a1", 250)], schema=SCHEMA)
    rows = up_accounts_repo.list_all(schema=SCHEMA)
    assert len(rows) == 1
    assert rows[0].balance_value == 250.0


def test_total_balance():
    up_accounts_repo.upsert_many([_acct("a1", 100), _acct("a2", 50.5)], schema=SCHEMA)
    assert up_accounts_repo.total_balance(schema=SCHEMA) == 150.5
