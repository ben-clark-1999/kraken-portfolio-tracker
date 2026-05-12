from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch, AsyncMock

import pytest

from backend.db.supabase_client import get_supabase
from backend.models.trading import IntervalTriggerEvent
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
    sl_mod._current_schema = SCHEMA
    yield
    sl_mod._current_schema = "public"


def _seed():
    sb = get_supabase()
    sid = sb.schema(SCHEMA).table("strategies").insert({
        "name": f"tf-{uuid4()}",
        "execution_mode": "llm_agent",
        "persona_key": "trend-follower",
        "starting_balance_aud": "1000",
        "trigger_config": {},
        "risk_caps": {"max_single_asset_pct": 30, "max_total_crypto_exposure_pct": 60,
                      "max_order_aud": 250, "daily_loss_cap_aud": 100,
                      "max_drawdown_pct_before_pause": 25,
                      "allowed_pairs": ["ETH/AUD"]},
    }).execute().data[0]["id"]
    sb.schema(SCHEMA).table("paper_positions").insert({
        "strategy_id": sid, "asset": "AUD",
        "qty": "1000", "avg_cost_aud": "1", "lots_jsonb": [],
    }).execute()
    return sid


@pytest.mark.asyncio
async def test_invoke_llm_strategy_writes_decision_with_persona_hash_and_cost():
    from backend.repositories import strategies_repo
    sid = _seed()
    strat = strategies_repo.get(sid, schema=SCHEMA)
    event = IntervalTriggerEvent(minutes=60, ts=datetime.now(timezone.utc))

    fake_response = {
        "agent_output": "No clear trend; holding cash.",
        "tool_calls": [],
        "input_tokens": 4_200,
        "output_tokens": 180,
        "model": "claude-sonnet-4-6",
    }

    with patch("backend.services.trading.llm_strategy._call_langgraph",
               new=AsyncMock(return_value=fake_response)), \
         patch("backend.services.trading.llm_strategy.aud_per_usd",
               return_value=Decimal("1.50")):
        from backend.services.trading.strategy_loop import invoke_llm_strategy
        await invoke_llm_strategy(strat, event)
    sb = get_supabase()
    row = (sb.schema(SCHEMA).table("agent_decisions").select("*")
             .eq("strategy_id", sid).order("created_at", desc=True)
             .limit(1).execute().data[0])
    assert row["execution_mode"] == "llm_agent"
    assert row["persona_prompt_hash"] is not None
    assert row["model"] == "claude-sonnet-4-6"
    assert row["input_tokens"] == 4_200
    assert Decimal(row["cost_aud"]) > Decimal("0")
