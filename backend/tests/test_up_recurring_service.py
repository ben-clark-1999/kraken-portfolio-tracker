from datetime import datetime, timedelta, timezone

import pytest
from backend.db.supabase_client import get_supabase
from backend.models.up import UpAccount, UpTransaction
from backend.repositories import up_accounts_repo, up_transactions_repo
from backend.services.up_recurring_service import find_recurring

SCHEMA = "test"


@pytest.fixture(autouse=True)
def _seed():
    db = get_supabase()
    db.schema(SCHEMA).table("up_transactions").delete().neq("id", "").execute()
    db.schema(SCHEMA).table("up_accounts").delete().neq("id", "").execute()
    up_accounts_repo.upsert_many([UpAccount(
        id="acct-1", display_name="X", account_type="TRANSACTIONAL", ownership_type="INDIVIDUAL",
        balance_value=0, created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )], schema=SCHEMA)
    yield


def _tx(id: str, amount: float, days_ago: int, description: str = "Spotify"):
    """Build a transaction `days_ago` days before now, with a fixed amount."""
    base = datetime.now(timezone.utc).replace(microsecond=0)
    when = base - timedelta(days=days_ago)
    return UpTransaction(
        id=id,
        account_id="acct-1",
        status="SETTLED",
        description=description,
        amount_value=-abs(amount),  # outflow
        category_id=None,
        parent_category_id=None,
        created_at=when,
        settled_at=when,
    )


def test_detects_5_monthly_netflix():
    txs = [_tx(f"n{i}", 16.99, 30 * i, "Netflix") for i in range(5)]
    up_transactions_repo.upsert_many(txs, schema=SCHEMA)

    results = find_recurring(schema=SCHEMA)

    assert len(results) == 1
    r = results[0]
    assert r.name.lower().startswith("netflix")
    assert r.cadence == "monthly"
    assert r.median_amount == 16.99
    assert r.occurrence_count == 5
    assert r.monthly_equivalent == 16.99


def test_detects_weekly_audible():
    txs = [_tx(f"a{i}", 4.99, 7 * i, "Audible") for i in range(4)]
    up_transactions_repo.upsert_many(txs, schema=SCHEMA)

    results = find_recurring(schema=SCHEMA)
    assert len(results) == 1
    assert results[0].cadence == "weekly"


def test_detects_yearly_with_two_charges():
    txs = [_tx("y0", 99.0, 0, "Apple iCloud"),
           _tx("y1", 99.0, 365, "Apple iCloud")]
    up_transactions_repo.upsert_many(txs, schema=SCHEMA)

    results = find_recurring(schema=SCHEMA)
    assert len(results) == 1
    r = results[0]
    assert r.cadence == "yearly"
    assert round(r.monthly_equivalent, 2) == 8.25


def test_skips_only_two_monthly_charges():
    txs = [_tx("s0", 11.99, 0, "Spotify"),
           _tx("s1", 11.99, 30, "Spotify")]
    up_transactions_repo.upsert_many(txs, schema=SCHEMA)
    assert find_recurring(schema=SCHEMA) == []


def test_skips_high_cv_amounts():
    amounts = [10, 50, 100, 30, 200]
    txs = [_tx(f"v{i}", a, 30 * i, "Coles") for i, a in enumerate(amounts)]
    up_transactions_repo.upsert_many(txs, schema=SCHEMA)
    assert find_recurring(schema=SCHEMA) == []


def test_skips_inactive_subscription():
    # 4 monthly charges but the most recent is 4 months old (> 2 cycles)
    txs = [_tx(f"d{i}", 9.99, 30 * i + 120, "Old Sub") for i in range(4)]
    up_transactions_repo.upsert_many(txs, schema=SCHEMA)
    assert find_recurring(schema=SCHEMA) == []


def test_skips_mixed_cadence_cluster():
    # Mix of intervals — 30, 7, 60, 14, 90 — no dominant bucket
    days = [0, 30, 37, 97, 111, 201]
    txs = [_tx(f"m{i}", 10.0, d, "Sporadic") for i, d in enumerate(days)]
    up_transactions_repo.upsert_many(txs, schema=SCHEMA)
    assert find_recurring(schema=SCHEMA) == []


def test_ignores_inflows():
    # Positive amounts (income) — should never be candidates
    base = datetime.now(timezone.utc).replace(microsecond=0)
    txs = [
        UpTransaction(
            id=f"i{i}", account_id="acct-1", status="SETTLED",
            description="Salary", amount_value=2000.0,  # POSITIVE
            category_id=None, parent_category_id=None,
            created_at=base - timedelta(days=30 * i),
            settled_at=base - timedelta(days=30 * i),
        )
        for i in range(5)
    ]
    up_transactions_repo.upsert_many(txs, schema=SCHEMA)
    assert find_recurring(schema=SCHEMA) == []


def test_results_sorted_by_monthly_equivalent_desc():
    spotify = [_tx(f"s{i}", 11.99, 30 * i, "Spotify") for i in range(3)]
    netflix = [_tx(f"n{i}", 16.99, 30 * i, "Netflix") for i in range(3)]
    audible = [_tx(f"a{i}", 4.99, 7 * i, "Audible") for i in range(4)]
    up_transactions_repo.upsert_many(spotify + netflix + audible, schema=SCHEMA)

    results = find_recurring(schema=SCHEMA)
    monthly_costs = [r.monthly_equivalent for r in results]
    assert monthly_costs == sorted(monthly_costs, reverse=True)
    assert results[0].name.lower().startswith("audible")  # ~$21.69/mo
