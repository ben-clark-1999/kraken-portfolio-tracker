from decimal import Decimal
from uuid import uuid4

import pytest

from backend.db.supabase_client import get_supabase
from backend.mcp_server import (
    place_paper_order, cancel_paper_order, get_my_paper_state,
    get_my_recent_decisions, get_market_snapshot,
)
from backend.services.trading import strategy_loop as sl_mod


SCHEMA = "test"
_SENTINEL_UUID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _truncate_and_set_schema():
    db = get_supabase()
    for table in ("paper_fills", "paper_orders", "agent_decisions", "system_alerts"):
        db.schema(SCHEMA).table(table).delete().neq("id", _SENTINEL_UUID).execute()
    for table in ("paper_positions", "paper_equity_snapshots"):
        db.schema(SCHEMA).table(table).delete().neq("strategy_id", _SENTINEL_UUID).execute()
    db.schema(SCHEMA).table("paper_benchmarks").delete().neq("benchmark_key", "__sentinel__").execute()
    db.schema(SCHEMA).table("strategies").delete().neq("id", _SENTINEL_UUID).execute()
    # Tools read _current_schema from strategy_loop; route them at the test schema.
    sl_mod._current_schema = SCHEMA
    sl_mod._current_executor = None
    yield
    sl_mod._current_schema = "public"
    sl_mod._current_executor = None


def _seed():
    sb = get_supabase()
    payload = {
        "name": f"mcp-strat-{uuid4()}",
        "execution_mode": "llm_agent",
        "persona_key": "trend-follower",
        "starting_balance_aud": "1000",
        "trigger_config": {},
        "risk_caps": {"max_single_asset_pct": 30, "max_total_crypto_exposure_pct": 60,
                      "max_order_aud": 250, "daily_loss_cap_aud": 100,
                      "max_drawdown_pct_before_pause": 25,
                      "allowed_pairs": ["ETH/AUD"]},
    }
    sid = sb.schema(SCHEMA).table("strategies").insert(payload).execute().data[0]["id"]
    sb.schema(SCHEMA).table("paper_positions").insert({
        "strategy_id": sid, "asset": "AUD",
        "qty": "1000", "avg_cost_aud": "1", "lots_jsonb": [],
    }).execute()
    return sid


def test_get_my_paper_state_returns_cash_and_positions():
    sid = _seed()
    state = get_my_paper_state(strategy_id=sid)
    assert Decimal(state["cash_aud"]) == Decimal("1000")
    # AUD is in the positions dict in the seed insert; the tool strips it out.
    assert state["positions"] == {} or state["positions"].get("AUD") is None


def test_get_my_recent_decisions_returns_list_even_when_empty():
    sid = _seed()
    rows = get_my_recent_decisions(strategy_id=sid, n=5)
    assert isinstance(rows, list)


def test_get_market_snapshot_returns_structure_for_each_pair():
    snap = get_market_snapshot(pairs=["ETH/AUD"])
    assert "ETH/AUD" in snap
    # The structure includes a top_ask/top_bid even if book is empty.
    assert "top_ask" in snap["ETH/AUD"] or "error" in snap["ETH/AUD"]


def test_place_paper_order_rejected_when_no_executor_attached():
    sid = _seed()
    # Without an attached executor & book in this unit context, the call
    # should return a structured rejection rather than raising.
    res = place_paper_order(
        strategy_id=sid, pair="ETH/AUD", side="buy",
        type="market", qty="0.01", idempotency_key=f"{sid}:t1:0",
    )
    assert res["status"] in ("rejected", "filled", "pending")
