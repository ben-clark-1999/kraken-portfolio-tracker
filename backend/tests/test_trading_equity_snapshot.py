from datetime import datetime, timedelta, timezone
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


def test_snapshot_all_active_auto_pauses_on_kill_criterion():
    sb = get_supabase()
    sid = sb.schema(SCHEMA).table("strategies").insert({
        "name": f"killable-{uuid4()}",
        "execution_mode": "llm_agent", "persona_key": "trend-follower",
        "starting_balance_aud": "1000",
        "trigger_config": {},
        "risk_caps": {"max_single_asset_pct": 30, "max_total_crypto_exposure_pct": 60,
                      "max_order_aud": 250, "daily_loss_cap_aud": 100,
                      "max_drawdown_pct_before_pause": 25,
                      "allowed_pairs": ["ETH/AUD"]},
        "kill_criteria": {
            "auto_pause_when": [
                {"metric": "drawdown_pct", "op": ">", "value": "10"},
            ],
        },
    }).execute().data[0]["id"]

    # Cash-only — equity = 700 AUD at the snapshot we are about to take.
    sb.schema(SCHEMA).table("paper_positions").insert([
        {"strategy_id": sid, "asset": "AUD",
         "qty": "700", "avg_cost_aud": "1", "lots_jsonb": []},
    ]).execute()

    # Seed a peak snapshot one hour ago at AUD 1000 so the snapshot taken
    # by snapshot_all_active draws the curve down to 700 (30% drawdown).
    peak_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    sb.schema(SCHEMA).table("paper_equity_snapshots").insert({
        "strategy_id": sid, "ts": peak_ts,
        "equity_aud": "1000", "cash_aud": "1000", "position_value_aud": "0",
        "realised_pnl_aud": "0", "unrealised_pnl_aud": "0",
    }).execute()

    snapshot_all_active(mids={}, schema=SCHEMA)

    refreshed = (sb.schema(SCHEMA).table("strategies")
                 .select("status").eq("id", sid).execute().data or [])
    assert refreshed and refreshed[0]["status"] == "paused"

    alerts = (sb.schema(SCHEMA).table("system_alerts").select("*")
              .eq("strategy_id", sid)
              .eq("code", "KILL_CRITERIA_AUTO_PAUSED").execute().data or [])
    assert len(alerts) == 1
    payload = alerts[0]["payload"]
    assert payload["metric"] == "drawdown_pct"


def test_snapshot_all_active_skips_pause_when_no_kill_criteria():
    sid = _seed_with_positions()
    # _seed_with_positions seeds no kill_criteria; default is empty list.
    snapshot_all_active(mids={"ETH/AUD": Decimal("3000")}, schema=SCHEMA)

    sb = get_supabase()
    refreshed = (sb.schema(SCHEMA).table("strategies")
                 .select("status").eq("id", sid).execute().data or [])
    assert refreshed and refreshed[0]["status"] == "active"

    alerts = (sb.schema(SCHEMA).table("system_alerts").select("*")
              .eq("strategy_id", sid).execute().data or [])
    assert len(alerts) == 0
