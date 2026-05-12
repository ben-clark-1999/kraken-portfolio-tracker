from decimal import Decimal
from uuid import uuid4

import pytest

from backend.db.supabase_client import get_supabase
from backend.services.trading.equity_snapshot import (
    compute_equity_for_strategy, snapshot_all_active,
)


SCHEMA = "test"
_SENTINEL_UUID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _truncate_paper_tables():
    db = get_supabase()
    for table in ("paper_fills", "paper_orders", "agent_decisions", "system_alerts"):
        db.schema(SCHEMA).table(table).delete().neq("id", _SENTINEL_UUID).execute()
    for table in ("paper_positions", "paper_equity_snapshots"):
        db.schema(SCHEMA).table(table).delete().neq("strategy_id", _SENTINEL_UUID).execute()
    db.schema(SCHEMA).table("paper_benchmarks").delete().neq("benchmark_key", "__sentinel__").execute()
    db.schema(SCHEMA).table("strategies").delete().neq("id", _SENTINEL_UUID).execute()
    yield


def _seed_with_positions():
    sb = get_supabase()
    sid = sb.schema(SCHEMA).table("strategies").insert({
        "name": f"eq-{uuid4()}",
        "execution_mode": "llm_agent", "persona_key": "trend-follower",
        "starting_balance_aud": "1000",
        "trigger_config": {},
        "risk_caps": {"max_single_asset_pct": 30, "max_total_crypto_exposure_pct": 60,
                      "max_order_aud": 250, "daily_loss_cap_aud": 100,
                      "max_drawdown_pct_before_pause": 25,
                      "allowed_pairs": ["ETH/AUD"]},
    }).execute().data[0]["id"]
    sb.schema(SCHEMA).table("paper_positions").insert([
        {"strategy_id": sid, "asset": "AUD",
         "qty": "500", "avg_cost_aud": "1", "lots_jsonb": []},
        {"strategy_id": sid, "asset": "ETH",
         "qty": "0.15", "avg_cost_aud": "3000",
         "lots_jsonb": [{"qty": "0.15", "cost_aud": "3000",
                         "acquired_at": "2026-05-01T00:00:00Z"}]},
    ]).execute()
    return sid


def test_compute_equity_uses_mid_for_position_value():
    sid = _seed_with_positions()
    eq = compute_equity_for_strategy(sid, mids={"ETH/AUD": Decimal("3200")},
                                     schema=SCHEMA)
    # cash 500 + 0.15 * 3200 = 500 + 480 = 980
    assert eq.equity_aud == Decimal("980")
    assert eq.cash_aud == Decimal("500")
    assert eq.position_value_aud == Decimal("480")


def test_snapshot_all_active_inserts_one_row_per_strategy():
    sid = _seed_with_positions()
    snapshot_all_active(mids={"ETH/AUD": Decimal("3000")}, schema=SCHEMA)
    sb = get_supabase()
    rows = (sb.schema(SCHEMA).table("paper_equity_snapshots").select("*")
              .eq("strategy_id", sid).execute().data or [])
    assert len(rows) >= 1
