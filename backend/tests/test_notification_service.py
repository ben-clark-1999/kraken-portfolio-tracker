"""Tests for NotificationService.maybe_notify.

We test against real Supabase test-schema rows (positions, strategies,
agent_decisions) and fake the ntfy HTTP layer with respx so the suite
stays hermetic.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
import respx

from backend.db.supabase_client import get_supabase
from backend.repositories import agent_decisions_repo
from backend.services.notifications import service as notif


SCHEMA = "test"
_SENTINEL_UUID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _truncate():
    db = get_supabase()
    for table in ("paper_fills", "paper_orders", "agent_decisions", "system_alerts"):
        db.schema(SCHEMA).table(table).delete().neq("id", _SENTINEL_UUID).execute()
    for table in ("paper_positions", "paper_equity_snapshots"):
        db.schema(SCHEMA).table(table).delete().neq("strategy_id", _SENTINEL_UUID).execute()
    db.schema(SCHEMA).table("strategies").delete().neq("id", _SENTINEL_UUID).execute()
    yield


def _seed_strategy(notify_enabled: bool, name: str = "trend",
                   execution_mode: str = "llm_agent") -> str:
    db = get_supabase()
    payload = {
        "name": f"{name}-{uuid4()}",
        "execution_mode": execution_mode,
        "starting_balance_aud": "1000",
        "trigger_config": {"triggers": [{"type": "cron", "expr": "0 9 * * *"}],
                           "debounce_seconds": 5, "cooldown_seconds": 900,
                           "max_calls_per_hour": 10},
        "risk_caps": {"max_single_asset_pct": 30, "max_total_crypto_exposure_pct": 60,
                      "max_order_aud": 250, "daily_loss_cap_aud": 100,
                      "max_drawdown_pct_before_pause": 25,
                      "allowed_pairs": ["ETH/AUD","SOL/AUD","LINK/AUD","ADA/AUD"]},
        "notify_enabled": notify_enabled,
    }
    if execution_mode == "llm_agent":
        payload["persona_key"] = "trend_follower"
    if execution_mode == "deterministic":
        payload["deterministic_config"] = {
            "cadence_cron": "0 9 */14 * *", "tz": "Australia/Sydney",
            "allocations": {"ETH/AUD": "0.50", "SOL/AUD": "0.25",
                            "LINK/AUD": "0.15", "ADA/AUD": "0.10"},
        }
    r = db.schema(SCHEMA).table("strategies").insert(payload).execute()
    sid = r.data[0]["id"]
    db.schema(SCHEMA).table("paper_positions").insert([
        {"strategy_id": sid, "asset": "AUD", "qty": "800",
         "avg_cost_aud": "1", "lots_jsonb": []},
        {"strategy_id": sid, "asset": "ETH", "qty": "0.052",
         "avg_cost_aud": "3450", "lots_jsonb": []},
    ]).execute()
    return sid


def _seed_decision(sid: str, *, tool_calls: list[dict],
                   agent_output: str | None = None) -> str:
    return agent_decisions_repo.insert(
        strategy_id=sid, execution_mode="llm_agent",
        trigger_event={"type": "cron", "expr": "0 9 * * *"},
        input_snapshot={}, persona_prompt_hash=None, model="claude-haiku-4-5",
        input_tokens=0, output_tokens=0, cost_aud=Decimal("0"),
        tool_calls=tool_calls, agent_output=agent_output,
        latency_ms=1, error=None, schema=SCHEMA,
    )


def _mock_books() -> dict:
    class _Lvl:
        def __init__(self, p, q): self.price, self.qty = Decimal(p), Decimal(q)
    class _Book:
        ts = datetime.now(timezone.utc)
        bids = [_Lvl("3449", "1")]
        asks = [_Lvl("3451", "1")]
        def mid(self): return Decimal("3450")
        def age_seconds(self, _): return 0
    return {"ETH/AUD": _Book()}


@pytest.mark.asyncio
async def test_no_notify_when_flag_false():
    sid = _seed_strategy(notify_enabled=False)
    decision_id = _seed_decision(sid, tool_calls=[{
        "tool": "place_paper_order",
        "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"},
    }], agent_output="<rationale>x</rationale>\n<confidence>medium</confidence>")
    with respx.mock(base_url="https://ntfy.sh",
                    assert_all_called=False,
                    assert_all_mocked=False) as router:
        router.route(host__regex=r".*supabase.*").pass_through()
        route = router.post("/test-topic").mock(return_value=httpx.Response(200))
        await notif.maybe_notify(
            decision_id=decision_id, strategy_id=sid,
            tool_calls=[{"tool": "place_paper_order",
                         "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"}}],
            agent_output="<confidence>medium</confidence>",
            schema=SCHEMA, books=_mock_books(),
            ntfy_topic="test-topic", ntfy_url_base="https://ntfy.sh",
            frontend_url="https://app.example.com",
        )
        assert route.call_count == 0


@pytest.mark.asyncio
async def test_no_notify_when_topic_blank():
    sid = _seed_strategy(notify_enabled=True)
    decision_id = _seed_decision(sid, tool_calls=[{
        "tool": "place_paper_order",
        "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"},
    }], agent_output="<confidence>medium</confidence>")
    with respx.mock(base_url="https://ntfy.sh",
                    assert_all_called=False,
                    assert_all_mocked=False) as router:
        router.route(host__regex=r".*supabase.*").pass_through()
        route = router.post("/").mock(return_value=httpx.Response(200))
        await notif.maybe_notify(
            decision_id=decision_id, strategy_id=sid,
            tool_calls=[{"tool": "place_paper_order",
                         "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"}}],
            agent_output="<confidence>medium</confidence>",
            schema=SCHEMA, books=_mock_books(),
            ntfy_topic="", ntfy_url_base="https://ntfy.sh",
            frontend_url="https://app.example.com",
        )
        assert route.call_count == 0


@pytest.mark.asyncio
async def test_happy_path_single_leg_posts_and_marks_notified():
    sb = get_supabase()
    sid = _seed_strategy(notify_enabled=True)
    decision_id = _seed_decision(sid, tool_calls=[{
        "tool": "place_paper_order",
        "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"},
    }], agent_output="<rationale>x</rationale>\n<confidence>high</confidence>")
    with respx.mock(base_url="https://ntfy.sh",
                    assert_all_called=False,
                    assert_all_mocked=False) as router:
        router.route(host__regex=r".*supabase.*").pass_through()
        route = router.post("/topic-abc").mock(return_value=httpx.Response(200))
        await notif.maybe_notify(
            decision_id=decision_id, strategy_id=sid,
            tool_calls=[{"tool": "place_paper_order",
                         "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"}}],
            agent_output="<confidence>high</confidence>",
            schema=SCHEMA, books=_mock_books(),
            ntfy_topic="topic-abc", ntfy_url_base="https://ntfy.sh",
            frontend_url="https://app.example.com",
        )
        assert route.call_count == 1
        body = route.calls.last.request.read().decode()
        assert "BUY ETH/AUD" in body
        assert "Confidence: high" in body
    row = (sb.schema(SCHEMA).table("agent_decisions")
             .select("notified_at").eq("id", decision_id).execute().data[0])
    assert row["notified_at"] is not None


@pytest.mark.asyncio
async def test_retries_once_then_alerts_on_persistent_failure():
    sb = get_supabase()
    sid = _seed_strategy(notify_enabled=True)
    decision_id = _seed_decision(sid, tool_calls=[{
        "tool": "place_paper_order",
        "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"},
    }], agent_output="<confidence>low</confidence>")
    with respx.mock(base_url="https://ntfy.sh",
                    assert_all_called=False,
                    assert_all_mocked=False) as router:
        router.route(host__regex=r".*supabase.*").pass_through()
        route = router.post("/topic-abc").mock(return_value=httpx.Response(500))
        await notif.maybe_notify(
            decision_id=decision_id, strategy_id=sid,
            tool_calls=[{"tool": "place_paper_order",
                         "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"}}],
            agent_output="<confidence>low</confidence>",
            schema=SCHEMA, books=_mock_books(),
            ntfy_topic="topic-abc", ntfy_url_base="https://ntfy.sh",
            frontend_url="https://app.example.com",
        )
        # One initial attempt + one retry.
        assert route.call_count == 2
    alerts = (sb.schema(SCHEMA).table("system_alerts")
                .select("*").eq("code", "PUSH_NOTIFY_FAILED").execute().data)
    assert len(alerts) == 1
    assert alerts[0]["payload"]["decision_id"] == decision_id


@pytest.mark.asyncio
async def test_idempotent_when_already_notified():
    sid = _seed_strategy(notify_enabled=True)
    decision_id = _seed_decision(sid, tool_calls=[{
        "tool": "place_paper_order",
        "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"},
    }], agent_output="<confidence>medium</confidence>")
    # Pre-mark as notified.
    agent_decisions_repo.mark_notified(decision_id, schema=SCHEMA)
    with respx.mock(base_url="https://ntfy.sh",
                    assert_all_called=False,
                    assert_all_mocked=False) as router:
        router.route(host__regex=r".*supabase.*").pass_through()
        route = router.post("/topic-abc").mock(return_value=httpx.Response(200))
        await notif.maybe_notify(
            decision_id=decision_id, strategy_id=sid,
            tool_calls=[{"tool": "place_paper_order",
                         "args": {"pair": "ETH/AUD", "side": "buy", "notional_aud": "100"}}],
            agent_output="<confidence>medium</confidence>",
            schema=SCHEMA, books=_mock_books(),
            ntfy_topic="topic-abc", ntfy_url_base="https://ntfy.sh",
            frontend_url="https://app.example.com",
        )
        assert route.call_count == 0


@pytest.mark.asyncio
async def test_ignores_non_place_paper_order_tool_calls():
    sid = _seed_strategy(notify_enabled=True)
    decision_id = _seed_decision(sid, tool_calls=[
        {"tool": "get_market_snapshot", "args": {"pair": "ETH/AUD"}},
        {"tool": "get_my_paper_state", "args": {}},
    ])
    with respx.mock(base_url="https://ntfy.sh",
                    assert_all_called=False,
                    assert_all_mocked=False) as router:
        router.route(host__regex=r".*supabase.*").pass_through()
        route = router.post("/topic-abc").mock(return_value=httpx.Response(200))
        await notif.maybe_notify(
            decision_id=decision_id, strategy_id=sid,
            tool_calls=[
                {"tool": "get_market_snapshot", "args": {"pair": "ETH/AUD"}},
                {"tool": "get_my_paper_state", "args": {}},
            ],
            agent_output=None, schema=SCHEMA, books=_mock_books(),
            ntfy_topic="topic-abc", ntfy_url_base="https://ntfy.sh",
            frontend_url="",
        )
        assert route.call_count == 0
