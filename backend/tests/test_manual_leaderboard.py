"""Integration tests for the leaderboard endpoint with Manual entry."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.db.supabase_client import get_supabase
from backend.main import app
from backend.services import kraken_service


SCHEMA = "public"  # leaderboard router uses public; tests accept that
_SENTINEL_UUID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def client(bypass_auth):
    return TestClient(app)


@pytest.fixture(autouse=True)
def _truncate_and_seed(monkeypatch):
    db = get_supabase()
    db.schema(SCHEMA).table("manual_cash_flows").delete().neq("id", _SENTINEL_UUID).execute()
    db.schema(SCHEMA).table("system_alerts").delete().neq("id", _SENTINEL_UUID).execute()
    kraken_service._user = None
    kraken_service._market = None
    # Don't truncate strategies/portfolio_snapshots in public — they're real prod data.
    # Use a monkeypatch on kraken_service.get_cash_flow_entries to control inputs.
    monkeypatch.setattr(
        kraken_service, "get_cash_flow_entries",
        lambda since=None: [],
    )
    yield


def test_leaderboard_includes_manual_row(client):
    r = client.get("/api/strategies/_leaderboard")
    assert r.status_code == 200
    rows = r.json()
    manual = [r for r in rows if r["id"] == "manual"]
    assert len(manual) == 1
    m = manual[0]
    assert m["name"] == "Manual"
    assert m["execution_mode"] == "manual"
    assert "return_all_time_pct" in m
    assert "lifetime_return_pct" in m
    assert "sharpe" in m
    assert "max_drawdown_pct" in m


def test_every_row_has_lifetime_return_pct(client):
    r = client.get("/api/strategies/_leaderboard")
    assert r.status_code == 200
    for row in r.json():
        assert "lifetime_return_pct" in row, f"missing on {row.get('name')}"


def test_rows_are_sorted_by_return_all_time_pct_desc(client):
    r = client.get("/api/strategies/_leaderboard")
    rows = r.json()
    pcts = [Decimal(row["return_all_time_pct"]) for row in rows]
    assert pcts == sorted(pcts, reverse=True), "leaderboard not sorted by return_all_time_pct desc"
