from datetime import datetime, timedelta, timezone

import pytest
from backend.db.supabase_client import get_supabase
from backend.models.up import UpAccount, UpCategory, UpTransaction
from backend.repositories import (
    up_accounts_repo, up_categories_repo, up_sync_log_repo, up_transactions_repo,
)
from backend.services import up_sync_service

SCHEMA = "test"


class FakeUpClient:
    def __init__(self, *, accounts=None, categories=None, transactions=None, raise_on_tx=None):
        self._accounts = accounts or []
        self._categories = categories or []
        self._transactions = transactions or []
        self._raise = raise_on_tx
        self.calls: list[tuple[str, dict]] = []

    async def list_accounts(self):
        self.calls.append(("accounts", {}))
        return list(self._accounts)

    async def list_categories(self):
        self.calls.append(("categories", {}))
        return list(self._categories)

    async def list_transactions(self, *, since=None, until=None, status=None):
        self.calls.append(("transactions", {"since": since, "until": until, "status": status}))
        if self._raise:
            raise self._raise
        for tx in self._transactions:
            if since and tx.created_at < since:
                continue
            yield tx


@pytest.fixture(autouse=True)
def _truncate():
    db = get_supabase()
    for t in ["up_transactions", "up_sync_log", "up_accounts", "up_categories"]:
        db.schema(SCHEMA).table(t).delete().neq("id", "00000000-0000-0000-0000-000000000001" if t == "up_sync_log" else "").execute()
    yield


def _acct():
    return UpAccount(
        id="acct-1", display_name="X", account_type="TRANSACTIONAL", ownership_type="INDIVIDUAL",
        balance_value=100.0, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _tx(id, days_ago):
    base = datetime(2026, 5, 1, tzinfo=timezone.utc)
    return UpTransaction(
        id=id, account_id="acct-1", status="SETTLED", description="x",
        amount_value=-1.0, category_id=None, parent_category_id=None,
        created_at=base - timedelta(days=days_ago),
        settled_at=base - timedelta(days=days_ago),
    )


@pytest.mark.asyncio
async def test_first_run_full_backfill():
    client = FakeUpClient(
        accounts=[_acct()],
        categories=[UpCategory(id="good-life", name="Good Life")],
        transactions=[_tx("t1", 30), _tx("t2", 10), _tx("t3", 1)],
    )
    await up_sync_service.sync(client=client, schema=SCHEMA)
    assert {a.id for a in up_accounts_repo.list_all(schema=SCHEMA)} == {"acct-1"}
    assert {c.id for c in up_categories_repo.get_all(schema=SCHEMA)} == {"good-life"}
    assert len(up_transactions_repo.list_recent(limit=10, schema=SCHEMA)) == 3
    last = up_sync_log_repo.last_successful_seen_tx_at(schema=SCHEMA)
    assert last is not None
    # First-run call to transactions should NOT pass `since`
    tx_call = next(c for c in client.calls if c[0] == "transactions")
    assert tx_call[1]["since"] is None


@pytest.mark.asyncio
async def test_incremental_uses_overlap_window():
    # Seed first run
    client1 = FakeUpClient(
        accounts=[_acct()], categories=[],
        transactions=[_tx("t1", 30)],
    )
    await up_sync_service.sync(client=client1, schema=SCHEMA)

    # Incremental
    client2 = FakeUpClient(
        accounts=[_acct()], categories=[],
        transactions=[_tx("t2", 1)],
    )
    await up_sync_service.sync(client=client2, schema=SCHEMA)
    tx_call = next(c for c in client2.calls if c[0] == "transactions")
    since = tx_call[1]["since"]
    last_seen = datetime(2026, 5, 1, tzinfo=timezone.utc) - timedelta(days=30)
    # Overlap window subtracts 6h
    assert since == last_seen - timedelta(hours=6)


@pytest.mark.asyncio
async def test_error_records_failure_log():
    client = FakeUpClient(accounts=[_acct()], raise_on_tx=Exception("boom"))
    with pytest.raises(Exception):
        await up_sync_service.sync(client=client, schema=SCHEMA)
    latest = up_sync_log_repo.latest(schema=SCHEMA)
    assert latest["status"] == "error"
    assert "boom" in (latest["error_message"] or "")
