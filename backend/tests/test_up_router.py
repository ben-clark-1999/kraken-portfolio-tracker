from datetime import datetime, timezone

from fastapi.testclient import TestClient
from backend.db.supabase_client import get_supabase
from backend.main import app
from backend.models.up import UpAccount
from backend.repositories import up_accounts_repo

SCHEMA = "test"
_SENTINEL = "00000000-0000-0000-0000-000000000001"
client = TestClient(app)


def _truncate():
    db = get_supabase()
    db.schema(SCHEMA).table("up_accounts").delete().neq("id", "").execute()


def test_list_accounts_returns_seeded_accounts(monkeypatch, bypass_auth):
    _truncate()
    monkeypatch.setattr("backend.routers.up.SCHEMA", SCHEMA)
    up_accounts_repo.upsert_many([
        UpAccount(id="a1", display_name="Spending", account_type="TRANSACTIONAL",
                  ownership_type="INDIVIDUAL", balance_value=100.0,
                  created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
    ], schema=SCHEMA)
    resp = client.get("/api/up/accounts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == "a1"
    assert data[0]["balance_value"] == 100.0


from datetime import timedelta
from backend.models.up import UpCategory, UpTransaction
from backend.repositories import up_categories_repo, up_transactions_repo


def _seed_with_tx(monkeypatch, bypass_auth):
    _truncate()
    db = get_supabase()
    db.schema(SCHEMA).table("up_transactions").delete().neq("id", "").execute()
    db.schema(SCHEMA).table("up_categories").delete().neq("id", "").execute()
    monkeypatch.setattr("backend.routers.up.SCHEMA", SCHEMA)

    up_accounts_repo.upsert_many([UpAccount(
        id="a1", display_name="X", account_type="TRANSACTIONAL", ownership_type="INDIVIDUAL",
        balance_value=0, created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )], schema=SCHEMA)
    up_categories_repo.upsert_many([
        UpCategory(id="good-life", name="Good Life"),
    ], schema=SCHEMA)

    base = datetime(2026, 5, 1, tzinfo=timezone.utc)
    txs = [
        UpTransaction(id=f"t{i}", account_id="a1", status="SETTLED",
                      description="Coffee", amount_value=-amt, parent_category_id="good-life",
                      created_at=base - timedelta(days=i),
                      settled_at=base - timedelta(days=i))
        for i, amt in enumerate([5, 10, 15], start=1)
    ]
    up_transactions_repo.upsert_many(txs, schema=SCHEMA)


def test_list_transactions(monkeypatch, bypass_auth):
    _seed_with_tx(monkeypatch, bypass_auth)
    resp = client.get("/api/up/transactions?limit=10")
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_spending_summary(monkeypatch, bypass_auth):
    _seed_with_tx(monkeypatch, bypass_auth)
    resp = client.get(
        "/api/up/spending/summary?since=2026-04-01T00:00:00Z&until=2026-06-01T00:00:00Z",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"good-life": 30.0}


def test_cashflow(monkeypatch, bypass_auth):
    _seed_with_tx(monkeypatch, bypass_auth)
    resp = client.get(
        "/api/up/cashflow?since=2026-04-01T00:00:00Z&until=2026-06-01T00:00:00Z&granularity=month",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body[-1]["expense"] == 30.0


def test_sync_status_returns_latest(monkeypatch, bypass_auth):
    monkeypatch.setattr("backend.routers.up.SCHEMA", SCHEMA)
    db = get_supabase()
    db.schema(SCHEMA).table("up_sync_log").delete().neq(
        "id", "00000000-0000-0000-0000-000000000001"
    ).execute()
    from backend.repositories import up_sync_log_repo
    sid = up_sync_log_repo.record_start(schema=SCHEMA)
    resp = client.get("/api/up/sync/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "syncing"
    up_sync_log_repo.finalize_success(sid, last_seen_tx_at=None, schema=SCHEMA)
    resp = client.get("/api/up/sync/status")
    assert resp.json()["state"] == "ready"


def test_sync_retry_returns_202(monkeypatch, bypass_auth):
    captured: list[bool] = []

    async def fake_sync():
        captured.append(True)

    monkeypatch.setattr("backend.routers.up.up_sync_service.sync", fake_sync)
    resp = client.post("/api/up/sync/retry")
    assert resp.status_code == 202


from datetime import timedelta as _td
from backend.models.up import UpAccount as _UpA, UpTransaction as _UpT


def test_recurring_endpoint(monkeypatch, bypass_auth):
    db = get_supabase()
    db.schema(SCHEMA).table("up_transactions").delete().neq("id", "").execute()
    db.schema(SCHEMA).table("up_accounts").delete().neq("id", "").execute()
    # The router calls up_recurring_service.find_recurring(schema=SCHEMA);
    # patching SCHEMA is enough to redirect to the test schema.
    monkeypatch.setattr("backend.routers.up.SCHEMA", SCHEMA)

    up_accounts_repo.upsert_many([_UpA(
        id="acct-1", display_name="X", account_type="TRANSACTIONAL", ownership_type="INDIVIDUAL",
        balance_value=0, created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )], schema=SCHEMA)

    base = datetime.now(timezone.utc).replace(microsecond=0)
    txs = [
        _UpT(
            id=f"r{i}", account_id="acct-1", status="SETTLED",
            description="Spotify", amount_value=-11.99,
            category_id=None, parent_category_id=None,
            created_at=base - _td(days=30 * i), settled_at=base - _td(days=30 * i),
        )
        for i in range(4)
    ]
    from backend.repositories import up_transactions_repo as _tx_repo
    _tx_repo.upsert_many(txs, schema=SCHEMA)

    resp = client.get("/api/up/recurring")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["cadence"] == "monthly"
    assert body[0]["name"].lower().startswith("spotify")
