from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.db.supabase_client import get_supabase
from backend.main import app


SCHEMA = "test"
_SENTINEL_UUID = "00000000-0000-0000-0000-000000000001"
client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_router(monkeypatch, bypass_auth):
    """Point the router at the test schema and skip auth."""
    monkeypatch.setattr("backend.routers.strategies.SCHEMA", SCHEMA)
    _truncate()
    yield
    _truncate()


def _truncate() -> None:
    db = get_supabase()
    for table in ("paper_fills", "paper_orders", "agent_decisions", "system_alerts"):
        db.schema(SCHEMA).table(table).delete().neq("id", _SENTINEL_UUID).execute()
    for table in ("paper_positions", "paper_equity_snapshots"):
        db.schema(SCHEMA).table(table).delete().neq("strategy_id", _SENTINEL_UUID).execute()
    db.schema(SCHEMA).table("paper_benchmarks").delete().neq(
        "benchmark_key", "__sentinel__").execute()
    db.schema(SCHEMA).table("strategies").delete().neq("id", _SENTINEL_UUID).execute()


def _seed_strategy(status: str = "active") -> str:
    sb = get_supabase()
    return sb.schema(SCHEMA).table("strategies").insert({
        "name": f"router-{uuid4()}",
        "execution_mode": "llm_agent",
        "persona_key": "trend-follower",
        "starting_balance_aud": "1000",
        "trigger_config": {},
        "risk_caps": {},
        "kill_criteria": {},
        "status": status,
    }).execute().data[0]["id"]


def test_list_strategies_returns_array():
    _seed_strategy()
    r = client.get("/api/strategies/")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert any(row["name"].startswith("router-") for row in body)


def test_get_strategy_returns_404_for_unknown():
    r = client.get(f"/api/strategies/{uuid4()}")
    assert r.status_code == 404


def test_get_strategy_returns_detail():
    sid = _seed_strategy()
    r = client.get(f"/api/strategies/{sid}")
    assert r.status_code == 200
    assert r.json()["id"] == sid


def test_pause_endpoint_updates_status():
    sid = _seed_strategy()
    r = client.post(f"/api/strategies/{sid}/pause")
    assert r.status_code == 200
    sb = get_supabase()
    row = sb.schema(SCHEMA).table("strategies").select("status").eq(
        "id", sid).execute().data[0]
    assert row["status"] == "paused"


def test_resume_endpoint_updates_status():
    sid = _seed_strategy(status="paused")
    r = client.post(f"/api/strategies/{sid}/resume")
    assert r.status_code == 200
    sb = get_supabase()
    row = sb.schema(SCHEMA).table("strategies").select("status").eq(
        "id", sid).execute().data[0]
    assert row["status"] == "active"


def test_leaderboard_returns_one_row_per_strategy():
    _seed_strategy()
    _seed_strategy()
    r = client.get("/api/strategies/_leaderboard")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    # 2 paper strategies + up to 2 always-on Manual virtual rows.
    paper_rows = [r for r in rows if r["execution_mode"] != "manual"]
    assert len(paper_rows) == 2
    row = paper_rows[0]
    assert "equity_aud" in row
    assert "sharpe" in row
    assert "trades" in row
    assert "return_7d_pct" in row
    assert "cost_30d_aud" in row


def test_decisions_endpoint_returns_list():
    sid = _seed_strategy()
    r = client.get(f"/api/strategies/{sid}/decisions?n=10")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_equity_curve_endpoint():
    sid = _seed_strategy()
    r = client.get(f"/api/strategies/{sid}/equity?range=7d")
    assert r.status_code == 200
    body = r.json()
    assert "strategy" in body
    assert "benchmarks" in body
    assert "btc_hodl" in body["benchmarks"]
    assert "alt_basket_equal_weight" in body["benchmarks"]
