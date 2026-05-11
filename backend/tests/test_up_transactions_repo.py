from datetime import datetime, timezone

import pytest
from backend.db.supabase_client import get_supabase
from backend.models.up import UpAccount, UpCategory, UpTransaction
from backend.repositories import up_accounts_repo, up_categories_repo, up_transactions_repo

SCHEMA = "test"


@pytest.fixture(autouse=True)
def _seed():
    db = get_supabase()
    db.schema(SCHEMA).table("up_transactions").delete().neq("id", "").execute()
    db.schema(SCHEMA).table("up_accounts").delete().neq("id", "").execute()
    db.schema(SCHEMA).table("up_categories").delete().neq("id", "").execute()
    up_accounts_repo.upsert_many([UpAccount(
        id="acct-1", display_name="X", account_type="TRANSACTIONAL", ownership_type="INDIVIDUAL",
        balance_value=0, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )], schema=SCHEMA)
    up_categories_repo.upsert_many([
        UpCategory(id="good-life", name="Good Life"),
        UpCategory(id="restaurants-and-cafes", name="Restaurants", parent_id="good-life"),
    ], schema=SCHEMA)
    yield


def _tx(id="t1", amount=-5.5, status="SETTLED", category="restaurants-and-cafes", parent="good-life"):
    return UpTransaction(
        id=id, account_id="acct-1", status=status, description="Coffee",
        amount_value=amount, category_id=category, parent_category_id=parent,
        created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        settled_at=datetime(2026, 4, 1, 1, tzinfo=timezone.utc) if status == "SETTLED" else None,
    )


def test_upsert_idempotent():
    up_transactions_repo.upsert_many([_tx("t1")], schema=SCHEMA)
    up_transactions_repo.upsert_many([_tx("t1")], schema=SCHEMA)
    assert len(up_transactions_repo.list_recent(limit=10, schema=SCHEMA)) == 1


def test_held_to_settled_updates_row():
    up_transactions_repo.upsert_many([_tx("t1", status="HELD")], schema=SCHEMA)
    up_transactions_repo.upsert_many([_tx("t1", status="SETTLED")], schema=SCHEMA)
    rows = up_transactions_repo.list_recent(limit=10, schema=SCHEMA)
    assert len(rows) == 1
    assert rows[0].status == "SETTLED"
    assert rows[0].settled_at is not None


def test_max_created_at():
    up_transactions_repo.upsert_many([
        _tx("t1"),
        UpTransaction(
            id="t2", account_id="acct-1", status="SETTLED", description="Other",
            amount_value=-1.0, category_id=None, parent_category_id=None,
            created_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            settled_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        ),
    ], schema=SCHEMA)
    latest = up_transactions_repo.max_created_at(schema=SCHEMA)
    assert latest is not None and latest.month == 5


def test_spending_by_parent_category_excludes_inflows():
    up_transactions_repo.upsert_many([
        _tx("t1", amount=-10),                             # outflow good-life
        _tx("t2", amount=-5),                              # outflow good-life
        _tx("t3", amount=200, category=None, parent=None), # inflow (salary), no category
    ], schema=SCHEMA)
    breakdown = up_transactions_repo.spending_by_parent_category(
        since=datetime(2026, 3, 1, tzinfo=timezone.utc),
        until=datetime(2026, 5, 1, tzinfo=timezone.utc),
        schema=SCHEMA,
    )
    assert breakdown == {"good-life": 15.0}


def test_row_to_tx_returns_aware_datetimes():
    """Datetime values returned from _row_to_tx must be timezone-aware so
    comparisons with max_created_at don't TypeError."""
    up_transactions_repo.upsert_many([
        UpTransaction(
            id="t1", account_id="acct-1", status="SETTLED", description="Coffee",
            amount_value=-5.5, category_id=None, parent_category_id=None,
            created_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
            settled_at=datetime(2026, 4, 1, 1, tzinfo=timezone.utc),
        ),
    ], schema=SCHEMA)
    txs = up_transactions_repo.list_recent(limit=10, schema=SCHEMA)
    latest = up_transactions_repo.max_created_at(schema=SCHEMA)
    assert txs[0].created_at.tzinfo is not None
    assert txs[0].settled_at.tzinfo is not None
    # Must be comparable without TypeError:
    assert txs[0].created_at <= latest
