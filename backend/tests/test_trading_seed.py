import pytest

from backend.db.supabase_client import get_supabase


SCHEMA = "test"
_SENTINEL_UUID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _truncate_seed_tables():
    db = get_supabase()
    for table in ("paper_fills", "paper_orders", "agent_decisions", "system_alerts"):
        db.schema(SCHEMA).table(table).delete().neq("id", _SENTINEL_UUID).execute()
    for table in ("paper_positions", "paper_equity_snapshots"):
        db.schema(SCHEMA).table(table).delete().neq("strategy_id", _SENTINEL_UUID).execute()
    db.schema(SCHEMA).table("paper_benchmarks").delete().neq(
        "benchmark_key", "__sentinel__").execute()
    db.schema(SCHEMA).table("strategies").delete().neq("id", _SENTINEL_UUID).execute()
    yield


def _strategies():
    sb = get_supabase()
    return sb.schema(SCHEMA).table("strategies").select("*").execute().data or []


def test_seed_dca_baseline_creates_deterministic_strategy():
    from backend.scripts.seed_strategies import seed_dca_baseline
    sid = seed_dca_baseline(schema=SCHEMA)
    sb = get_supabase()
    row = sb.schema(SCHEMA).table("strategies").select("*").eq(
        "id", sid).execute().data[0]
    assert row["execution_mode"] == "deterministic"
    cfg = row["deterministic_config"]
    assert cfg["allocations"]["ETH/AUD"] == "0.50"


def test_seed_trend_follower_creates_llm_strategy_with_persona():
    from backend.scripts.seed_strategies import seed_trend_follower
    sid = seed_trend_follower(schema=SCHEMA)
    sb = get_supabase()
    row = sb.schema(SCHEMA).table("strategies").select("*").eq(
        "id", sid).execute().data[0]
    assert row["execution_mode"] == "llm_agent"
    assert row["persona_key"] == "trend-follower"


def test_seed_mean_reverter_creates_llm_strategy_with_persona():
    from backend.scripts.seed_strategies import seed_mean_reverter
    sid = seed_mean_reverter(schema=SCHEMA)
    sb = get_supabase()
    row = sb.schema(SCHEMA).table("strategies").select("*").eq(
        "id", sid).execute().data[0]
    assert row["persona_key"] == "mean-reverter"


def test_seed_all_is_idempotent_by_name():
    from backend.scripts.seed_strategies import seed_all
    seed_all(schema=SCHEMA)
    count1 = len([s for s in _strategies()
                  if s["name"] in ("DCA-Baseline", "Trend-Follower", "Mean-Reverter")])
    seed_all(schema=SCHEMA)
    count2 = len([s for s in _strategies()
                  if s["name"] in ("DCA-Baseline", "Trend-Follower", "Mean-Reverter")])
    assert count1 == count2 == 3


def test_seed_dca_baseline_seeds_cash_position():
    from backend.scripts.seed_strategies import seed_dca_baseline
    sid = seed_dca_baseline(schema=SCHEMA)
    sb = get_supabase()
    rows = sb.schema(SCHEMA).table("paper_positions").select("*").eq(
        "strategy_id", sid).eq("asset", "AUD").execute().data or []
    assert len(rows) == 1
    assert float(rows[0]["qty"]) == 1000.0


def test_seed_dca_baseline_is_weekly_dca_mode():
    from backend.scripts.seed_strategies import seed_dca_baseline
    from backend.db.supabase_client import get_supabase
    sid = seed_dca_baseline(schema=SCHEMA)
    row = (get_supabase().schema(SCHEMA).table("strategies")
           .select("*").eq("id", sid).execute().data[0])
    cfg = row["deterministic_config"]
    assert cfg["mode"] == "dca"
    assert cfg["num_buys"] == 12
    assert cfg["cadence_cron"] == "0 9 * * 1"
    # Weekly cron trigger present.
    assert any(t.get("expr") == "0 9 * * 1"
               for t in row["trigger_config"]["triggers"] if t["type"] == "cron")
    assert row["risk_caps"]["max_single_asset_pct"] == 100
    assert row["kill_criteria"]["auto_pause_when"] == []


def test_seed_trend_rule_is_deterministic_daily():
    from backend.scripts.seed_strategies import seed_trend_rule
    from backend.db.supabase_client import get_supabase
    sid = seed_trend_rule(schema=SCHEMA)
    row = (get_supabase().schema(SCHEMA).table("strategies")
           .select("*").eq("id", sid).execute().data[0])
    assert row["execution_mode"] == "deterministic"
    cfg = row["deterministic_config"]
    assert cfg["mode"] == "trend_rule"
    assert set(cfg["universe"]) == {"ETH/AUD", "SOL/AUD", "LINK/AUD", "ADA/AUD"}
    assert cfg["cadence_cron"] == "0 9 * * *"
    assert str(cfg["min_move_pct"]) == "1.5"


def test_seed_mean_reversion_rule_is_deterministic_daily():
    from backend.scripts.seed_strategies import seed_mean_reversion_rule
    from backend.db.supabase_client import get_supabase
    sid = seed_mean_reversion_rule(schema=SCHEMA)
    row = (get_supabase().schema(SCHEMA).table("strategies")
           .select("*").eq("id", sid).execute().data[0])
    cfg = row["deterministic_config"]
    assert cfg["mode"] == "mean_reversion_rule"
    assert str(cfg["entry_z"]) == "-2"
    assert str(cfg["exit_z"]) == "0"


def test_seed_all_creates_five_strategies():
    from backend.scripts.seed_strategies import seed_all
    from backend.db.supabase_client import get_supabase
    seed_all(schema=SCHEMA)
    names = {r["name"] for r in get_supabase().schema(SCHEMA).table("strategies")
             .select("name").execute().data}
    assert {"DCA-Baseline", "Trend-Follower", "Mean-Reverter",
            "Trend-Rule", "Mean-Reversion-Rule"} <= names
