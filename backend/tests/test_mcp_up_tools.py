"""Smoke tests for new UP MCP tools — direct function invocation,
bypassing the MCP transport layer."""

import importlib

from datetime import datetime, timezone

from backend.db.supabase_client import get_supabase
from backend.models.up import UpAccount
from backend.repositories import up_accounts_repo

SCHEMA = "test"


def _truncate():
    get_supabase().schema(SCHEMA).table("up_accounts").delete().neq("id", "").execute()


def test_get_up_balance_returns_total(monkeypatch):
    _truncate()
    import backend.mcp_server as mcp_module
    monkeypatch.setattr(mcp_module, "UP_SCHEMA", SCHEMA)
    up_accounts_repo.upsert_many([
        UpAccount(id="a1", display_name="X", account_type="TRANSACTIONAL",
                  ownership_type="INDIVIDUAL", balance_value=150.0,
                  created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
    ], schema=SCHEMA)
    out = mcp_module.get_up_balance()
    assert "150" in out
    assert "AUD" in out


def test_get_combined_net_worth(monkeypatch):
    import backend.mcp_server as mcp_module
    monkeypatch.setattr(mcp_module, "UP_SCHEMA", SCHEMA)
    monkeypatch.setattr(mcp_module, "_crypto_value", lambda: 10_000.0)
    out = mcp_module.get_combined_net_worth()
    assert "10" in out  # mentions crypto component
    assert "AUD" in out


from datetime import timedelta as _td2
from backend.models.up import UpAccount as _UpA2, UpTransaction as _UpT2
from backend.repositories import up_accounts_repo as _acc_repo, up_transactions_repo as _tx_repo


def test_get_recurring_charges_includes_monthly_total(monkeypatch):
    db = get_supabase()
    db.schema(SCHEMA).table("up_transactions").delete().neq("id", "").execute()
    db.schema(SCHEMA).table("up_accounts").delete().neq("id", "").execute()

    import backend.mcp_server as mcp_module
    # The MCP tool calls find_recurring(schema=UP_SCHEMA); patching UP_SCHEMA
    # is enough to redirect reads to the test schema.
    monkeypatch.setattr(mcp_module, "UP_SCHEMA", SCHEMA)

    _acc_repo.upsert_many([_UpA2(
        id="acct-1", display_name="X", account_type="TRANSACTIONAL", ownership_type="INDIVIDUAL",
        balance_value=0, created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )], schema=SCHEMA)

    base = datetime.now(timezone.utc).replace(microsecond=0)
    txs = [
        _UpT2(id=f"x{i}", account_id="acct-1", status="SETTLED",
              description="Spotify", amount_value=-11.99,
              category_id=None, parent_category_id=None,
              created_at=base - _td2(days=30 * i), settled_at=base - _td2(days=30 * i))
        for i in range(4)
    ]
    _tx_repo.upsert_many(txs, schema=SCHEMA)

    out = mcp_module.get_recurring_charges()
    assert "Spotify" in out
    assert "monthly" in out.lower()
    assert "11.99" in out
    assert "/month" in out  # the heading line
