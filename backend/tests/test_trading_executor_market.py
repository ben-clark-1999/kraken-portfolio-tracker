"""Integration tests for PaperExecutor market-order path.

Hits the project's `test` schema (see supabase/migrations/test_006_paper_trading.sql).
A per-test fixture truncates the paper_* tables before and after each case.
"""
from decimal import Decimal
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from backend.db.supabase_client import get_supabase
from backend.models.trading import OrderBookLevel
from backend.services.trading.executor import PaperExecutor
from backend.services.trading.order_book import LocalOrderBook


SCHEMA = "test"
_SENTINEL_UUID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture(autouse=True)
def _truncate_paper_tables():
    db = get_supabase()
    # Tables with a single `id` PK can use neq("id", sentinel). Composite-PK
    # tables need a column that's always present — use strategy_id for the
    # strategy-scoped ones and benchmark_key for paper_benchmarks.
    for table in ("paper_fills", "paper_orders", "agent_decisions", "system_alerts"):
        db.schema(SCHEMA).table(table).delete().neq("id", _SENTINEL_UUID).execute()
    for table in ("paper_positions", "paper_equity_snapshots"):
        db.schema(SCHEMA).table(table).delete().neq("strategy_id", _SENTINEL_UUID).execute()
    db.schema(SCHEMA).table("paper_benchmarks").delete().neq("benchmark_key", "__sentinel__").execute()
    db.schema(SCHEMA).table("strategies").delete().neq("id", _SENTINEL_UUID).execute()
    yield


def _seed_strategy(starting=Decimal("1000"), allowed_pairs=None) -> str:
    sb = get_supabase()
    payload = {
        "name": f"test-strat-{uuid4()}",
        "execution_mode": "llm_agent",
        "persona_key": "trend-follower",
        "starting_balance_aud": str(starting),
        "trigger_config": {"triggers": [], "debounce_seconds": 5,
                           "cooldown_seconds": 900, "max_calls_per_hour": 10},
        "risk_caps": {"max_single_asset_pct": 30, "max_total_crypto_exposure_pct": 60,
                      "max_order_aud": 250, "daily_loss_cap_aud": 100,
                      "max_drawdown_pct_before_pause": 25,
                      "allowed_pairs": allowed_pairs or ["ETH/AUD"]},
        "status": "active",
    }
    r = sb.schema(SCHEMA).table("strategies").insert(payload).execute()
    sid = r.data[0]["id"]
    # Seed AUD cash position.
    sb.schema(SCHEMA).table("paper_positions").insert({
        "strategy_id": sid, "asset": "AUD",
        "qty": str(starting), "avg_cost_aud": "1",
        "lots_jsonb": [],
    }).execute()
    return sid


def _attached_book(pair="ETH/AUD"):
    ob = LocalOrderBook(pair)
    ob.apply_snapshot(
        asks=[OrderBookLevel(price=Decimal("3000"), qty=Decimal("0.05")),
              OrderBookLevel(price=Decimal("3001"), qty=Decimal("0.1"))],
        bids=[OrderBookLevel(price=Decimal("2999"), qty=Decimal("1")),
              OrderBookLevel(price=Decimal("2998"), qty=Decimal("1"))],
        checksum="snap-test", ts=datetime.now(timezone.utc),
    )
    return ob


def _executor():
    pe = PaperExecutor(schema=SCHEMA)
    pe.attach_book("ETH/AUD", _attached_book())
    return pe


@pytest.mark.asyncio
async def test_market_buy_within_caps_creates_filled_order_and_fills():
    sid = _seed_strategy()
    pe = _executor()
    res = await pe.submit_order(
        strategy_id=sid, idempotency_key=f"{sid}:t1:0",
        pair="ETH/AUD", side="buy", type="market",
        qty=Decimal("0.04"),
    )
    assert res.status == "filled"
    assert len(res.fills) >= 1
    sb = get_supabase()
    fills = (sb.schema(SCHEMA).table("paper_fills").select("*").execute().data or [])
    # qty 0.04 fits inside the first ask level (0.05 @ 3000) → one fill
    assert any(f for f in fills if Decimal(f["price"]) == Decimal("3000"))


@pytest.mark.asyncio
async def test_market_buy_rejected_when_exceeds_max_order_aud():
    sid = _seed_strategy()
    pe = _executor()
    # 0.1 ETH @ 3000 = 300 notional > 250 cap
    res = await pe.submit_order(
        strategy_id=sid, idempotency_key=f"{sid}:t2:0",
        pair="ETH/AUD", side="buy", type="market",
        qty=Decimal("0.1"),
    )
    assert res.status == "rejected"
    assert res.reject_reason == "MAX_ORDER_AUD"


@pytest.mark.asyncio
async def test_market_buy_rejected_when_pair_not_allowed():
    sid = _seed_strategy(allowed_pairs=["LINK/AUD"])
    pe = _executor()
    res = await pe.submit_order(
        strategy_id=sid, idempotency_key=f"{sid}:t3:0",
        pair="ETH/AUD", side="buy", type="market",
        qty=Decimal("0.01"),
    )
    assert res.status == "rejected"
    assert res.reject_reason == "PAIR_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_market_rejected_when_book_stale():
    sid = _seed_strategy()
    pe = PaperExecutor(schema=SCHEMA)
    stale = LocalOrderBook("ETH/AUD")
    stale.apply_snapshot(
        asks=[OrderBookLevel(price=Decimal("3000"), qty=Decimal("1"))],
        bids=[OrderBookLevel(price=Decimal("2999"), qty=Decimal("1"))],
        checksum="snap-stale",
        ts=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    pe.attach_book("ETH/AUD", stale)
    res = await pe.submit_order(
        strategy_id=sid, idempotency_key=f"{sid}:t4:0",
        pair="ETH/AUD", side="buy", type="market",
        qty=Decimal("0.01"),
    )
    assert res.status == "rejected"
    assert res.reject_reason == "BOOK_UNAVAILABLE"


@pytest.mark.asyncio
async def test_market_idempotency_same_key_returns_cached_result():
    sid = _seed_strategy()
    pe = _executor()
    key = f"{sid}:t5:0"
    r1 = await pe.submit_order(
        strategy_id=sid, idempotency_key=key,
        pair="ETH/AUD", side="buy", type="market",
        qty=Decimal("0.01"),
    )
    r2 = await pe.submit_order(
        strategy_id=sid, idempotency_key=key,
        pair="ETH/AUD", side="buy", type="market",
        qty=Decimal("0.01"),
    )
    assert r1.order_id == r2.order_id
    sb = get_supabase()
    rows = (sb.schema(SCHEMA).table("paper_orders")
              .select("*").eq("idempotency_key", key).execute().data)
    assert len(rows) == 1   # not double-inserted
