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
