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
