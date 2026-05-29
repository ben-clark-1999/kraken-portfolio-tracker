from uuid import uuid4

import pytest

from backend.db.supabase_client import get_supabase

SCHEMA = "test"
_SENTINEL = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def _seeded(monkeypatch):
    # Point the router at the test schema (leaderboard() reads module-level SCHEMA).
    import backend.routers.strategies as r
    monkeypatch.setattr(r, "SCHEMA", SCHEMA)
    sb = get_supabase()
    for t in ("paper_fills", "paper_orders", "agent_decisions"):
        sb.schema(SCHEMA).table(t).delete().neq("id", _SENTINEL).execute()
    sb.schema(SCHEMA).table("paper_positions").delete().neq("strategy_id", _SENTINEL).execute()
    sb.schema(SCHEMA).table("strategies").delete().neq("id", _SENTINEL).execute()
    sid = sb.schema(SCHEMA).table("strategies").insert({
        "name": "T", "execution_mode": "deterministic",
        "deterministic_config": {"cadence_cron": "0 9 * * 1", "allocations": {"ETH/AUD": "1.0"}},
        "starting_balance_aud": "1000", "status": "active"}).execute().data[0]["id"]
    # 1 filled, 1 partial, 2 rejected, 1 cancelled → count should be 2.
    for st in ("filled", "partial", "rejected", "rejected", "cancelled"):
        sb.schema(SCHEMA).table("paper_orders").insert({
            "strategy_id": sid, "idempotency_key": f"k-{st}-{uuid4().hex[:8]}",
            "pair": "ETH/AUD", "side": "buy", "type": "market",
            "qty": "0.1", "status": st}).execute()
    return sid


def test_leaderboard_trades_counts_executions_only(_seeded):
    # leaderboard() is a plain function; the require_auth dependency lives on the
    # router, so calling it directly needs no auth bypass.
    from backend.routers.strategies import leaderboard
    rows = leaderboard()
    row = next(r for r in rows if r["name"] == "T")
    assert row["trades"] == 2
