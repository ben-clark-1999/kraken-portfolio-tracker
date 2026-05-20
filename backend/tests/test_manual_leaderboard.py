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
    # The leaderboard router uses the public schema, so these tests run
    # against real prod data. The assertions are deliberately loose (field
    # presence, basic shape) and do NOT depend on table state — so we must
    # NEVER mutate public-schema rows here. Stub out the Kraken calls so
    # no new cash flows or alerts get written either.
    kraken_service._user = None
    kraken_service._market = None
    monkeypatch.setattr(
        kraken_service, "get_cash_flow_entries",
        lambda since=None: [],
    )
    monkeypatch.setattr(
        kraken_service, "get_all_ledger_entries",
        lambda: [],
    )
    monkeypatch.setattr(
        kraken_service, "get_trade_history",
        lambda since_trade_id=None: [],
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
