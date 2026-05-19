from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.db.supabase_client import get_supabase
from backend.models.trading import CronTriggerEvent
from backend.services.trading.decision_writer import write_agent_decision
from backend.services.trading.strategy_loop import (
    invoke_deterministic_strategy, set_executor,
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
    # Reset module-level executor between tests.
    yield
    set_executor(None, schema="public")


def _seed_dca_strategy():
    sb = get_supabase()
    payload = {
        "name": f"dca-{uuid4()}",
        "execution_mode": "deterministic",
        "deterministic_config": {
            "cadence_cron": "0 9 */14 * *", "tz": "Australia/Sydney",
            "allocations": {"ETH/AUD": "0.50", "SOL/AUD": "0.25",
                            "LINK/AUD": "0.15", "ADA/AUD": "0.10"},
        },
        "starting_balance_aud": "1000",
        "trigger_config": {"triggers": [{"type": "cron",
                                         "expr": "0 9 */14 * *"}],
                           "debounce_seconds": 5, "cooldown_seconds": 900,
                           "max_calls_per_hour": 10},
        "risk_caps": {"max_single_asset_pct": 30, "max_total_crypto_exposure_pct": 60,
                      "max_order_aud": 250, "daily_loss_cap_aud": 100,
                      "max_drawdown_pct_before_pause": 25,
                      "allowed_pairs": ["ETH/AUD","SOL/AUD","LINK/AUD","ADA/AUD"]},
    }
    r = sb.schema(SCHEMA).table("strategies").insert(payload).execute()
    sid = r.data[0]["id"]
    sb.schema(SCHEMA).table("paper_positions").insert({
        "strategy_id": sid, "asset": "AUD",
        "qty": "1000", "avg_cost_aud": "1", "lots_jsonb": [],
    }).execute()
    return sid


def test_write_agent_decision_inserts_row():
    sb = get_supabase()
    sid = _seed_dca_strategy()
    decision_id = write_agent_decision(
        strategy_id=sid, execution_mode="deterministic",
        trigger_event={"type": "cron", "expr": "0 9 * * *"},
        input_snapshot={"cash": "1000"},
        persona_prompt_hash=None, model=None,
        input_tokens=0, output_tokens=0, cost_aud=Decimal("0"),
        tool_calls=[], agent_output=None, latency_ms=10, error=None,
        schema=SCHEMA,
    )
    r = sb.schema(SCHEMA).table("agent_decisions").select("*").eq("id", decision_id).execute()
    assert r.data[0]["execution_mode"] == "deterministic"


@pytest.mark.asyncio
async def test_invoke_deterministic_strategy_emits_orders_and_decision_row():
    from backend.repositories import strategies_repo
    sid = _seed_dca_strategy()
    strat = strategies_repo.get(sid, schema=SCHEMA)

    calls = []

    class FakeExecutor:
        _books = {}   # no books — deterministic path falls back to avg_cost mids
        async def submit_order(self, **kw):
            calls.append(kw)
            from backend.models.trading import OrderResult
            return OrderResult(order_id=str(uuid4()), status="filled")

    set_executor(FakeExecutor(), schema=SCHEMA)

    event = CronTriggerEvent(expr="0 9 */14 * *",
                             ts=datetime.now(timezone.utc))
    await invoke_deterministic_strategy(strat, event)
    assert len(calls) == 4   # one order per pair on first rebalance
    sb = get_supabase()
    rows = (sb.schema(SCHEMA).table("agent_decisions").select("*")
              .eq("strategy_id", sid).execute().data or [])
    assert any(r["execution_mode"] == "deterministic" for r in rows)


def test_strategy_row_loads_notify_enabled_default_false():
    from backend.repositories import strategies_repo
    sid = _seed_dca_strategy()
    strat = strategies_repo.get(sid, schema=SCHEMA)
    assert strat.notify_enabled is False


def test_strategy_row_loads_notify_enabled_when_true():
    from backend.repositories import strategies_repo
    sid = _seed_dca_strategy()
    db = get_supabase()
    db.schema(SCHEMA).table("strategies").update(
        {"notify_enabled": True}
    ).eq("id", sid).execute()
    strat = strategies_repo.get(sid, schema=SCHEMA)
    assert strat.notify_enabled is True


def test_mark_notified_sets_timestamp_when_null():
    from backend.repositories import agent_decisions_repo
    sb = get_supabase()
    sid = _seed_dca_strategy()
    decision_id = write_agent_decision(
        strategy_id=sid, execution_mode="deterministic",
        trigger_event={"type": "cron", "expr": "0 9 * * *"},
        input_snapshot={}, persona_prompt_hash=None, model=None,
        input_tokens=0, output_tokens=0, cost_aud=Decimal("0"),
        tool_calls=[], agent_output=None, latency_ms=1, error=None,
        schema=SCHEMA,
    )

    result = agent_decisions_repo.mark_notified(decision_id, schema=SCHEMA)
    assert result is True
    row = (sb.schema(SCHEMA).table("agent_decisions")
             .select("notified_at").eq("id", decision_id).execute().data[0])
    assert row["notified_at"] is not None


def test_mark_notified_is_idempotent_when_already_set():
    from backend.repositories import agent_decisions_repo
    sb = get_supabase()
    sid = _seed_dca_strategy()
    decision_id = write_agent_decision(
        strategy_id=sid, execution_mode="deterministic",
        trigger_event={"type": "cron", "expr": "0 9 * * *"},
        input_snapshot={}, persona_prompt_hash=None, model=None,
        input_tokens=0, output_tokens=0, cost_aud=Decimal("0"),
        tool_calls=[], agent_output=None, latency_ms=1, error=None,
        schema=SCHEMA,
    )
    assert agent_decisions_repo.mark_notified(decision_id, schema=SCHEMA) is True
    first = (sb.schema(SCHEMA).table("agent_decisions")
               .select("notified_at").eq("id", decision_id).execute().data[0]["notified_at"])
    # Second call: no-op, returns False.
    assert agent_decisions_repo.mark_notified(decision_id, schema=SCHEMA) is False
    second = (sb.schema(SCHEMA).table("agent_decisions")
                .select("notified_at").eq("id", decision_id).execute().data[0]["notified_at"])
    assert first == second
