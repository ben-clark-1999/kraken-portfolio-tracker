from datetime import datetime, timedelta, timezone
from decimal import Decimal
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
    for table in ("paper_fills", "paper_orders", "agent_decisions", "system_alerts"):
        db.schema(SCHEMA).table(table).delete().neq("id", _SENTINEL_UUID).execute()
    for table in ("paper_positions", "paper_equity_snapshots"):
        db.schema(SCHEMA).table(table).delete().neq("strategy_id", _SENTINEL_UUID).execute()
    db.schema(SCHEMA).table("paper_benchmarks").delete().neq("benchmark_key", "__sentinel__").execute()
    db.schema(SCHEMA).table("strategies").delete().neq("id", _SENTINEL_UUID).execute()
    yield


def _seed_strategy():
    sb = get_supabase()
    payload = {
        "name": f"limit-strat-{uuid4()}",
        "execution_mode": "llm_agent",
        "persona_key": "trend-follower",
        "starting_balance_aud": "1000",
        "trigger_config": {},
        "risk_caps": {"max_single_asset_pct": 30, "max_total_crypto_exposure_pct": 60,
                      "max_order_aud": 250, "daily_loss_cap_aud": 100,
                      "max_drawdown_pct_before_pause": 25,
                      "allowed_pairs": ["ETH/AUD"]},
    }
    r = sb.schema(SCHEMA).table("strategies").insert(payload).execute()
    sid = r.data[0]["id"]
    sb.schema(SCHEMA).table("paper_positions").insert({
        "strategy_id": sid, "asset": "AUD",
        "qty": "1000", "avg_cost_aud": "1", "lots_jsonb": [],
    }).execute()
    return sid


def _book():
    ob = LocalOrderBook("ETH/AUD")
    ob.apply_snapshot(
        asks=[OrderBookLevel(price=Decimal("3000"), qty=Decimal("1"))],
        bids=[OrderBookLevel(price=Decimal("2999"), qty=Decimal("1"))],
        checksum="x", ts=datetime.now(timezone.utc),
    )
    return ob


@pytest.mark.asyncio
async def test_limit_buy_below_market_rests_as_pending():
    sid = _seed_strategy()
    pe = PaperExecutor(schema=SCHEMA)
    pe.attach_book("ETH/AUD", _book())
    res = await pe.submit_order(
        strategy_id=sid, idempotency_key=f"{sid}:lim1:0",
        pair="ETH/AUD", side="buy", type="limit",
        qty=Decimal("0.05"), limit_price=Decimal("2900"),
    )
    assert res.status == "pending"
    assert res.fills == []


@pytest.mark.asyncio
async def test_limit_buy_above_market_fills_immediately_capped_at_limit():
    sid = _seed_strategy()
    pe = PaperExecutor(schema=SCHEMA)
    pe.attach_book("ETH/AUD", _book())
    res = await pe.submit_order(
        strategy_id=sid, idempotency_key=f"{sid}:lim2:0",
        pair="ETH/AUD", side="buy", type="limit",
        qty=Decimal("0.05"), limit_price=Decimal("3100"),
    )
    assert res.status == "filled"
    assert all(f.fee_role == "taker" for f in res.fills)


@pytest.mark.asyncio
async def test_limit_default_expires_at_24h():
    sid = _seed_strategy()
    pe = PaperExecutor(schema=SCHEMA)
    pe.attach_book("ETH/AUD", _book())
    res = await pe.submit_order(
        strategy_id=sid, idempotency_key=f"{sid}:lim3:0",
        pair="ETH/AUD", side="buy", type="limit",
        qty=Decimal("0.05"), limit_price=Decimal("2900"),
    )
    sb = get_supabase()
    row = sb.schema(SCHEMA).table("paper_orders").select("*").eq("id", res.order_id).execute().data[0]
    expires = datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
    assert timedelta(hours=23) < expires - datetime.now(timezone.utc) <= timedelta(hours=24, minutes=1)


@pytest.mark.asyncio
async def test_reconciler_fills_pending_limit_when_book_crosses():
    sid = _seed_strategy()
    pe = PaperExecutor(schema=SCHEMA)
    book = _book()
    pe.attach_book("ETH/AUD", book)
    res = await pe.submit_order(
        strategy_id=sid, idempotency_key=f"{sid}:lim4:0",
        pair="ETH/AUD", side="buy", type="limit",
        qty=Decimal("0.05"), limit_price=Decimal("2950"),
    )
    assert res.status == "pending"
    # Book moves down so 2950 now crosses.
    book.apply_snapshot(
        asks=[OrderBookLevel(price=Decimal("2940"), qty=Decimal("1"))],
        bids=[OrderBookLevel(price=Decimal("2939"), qty=Decimal("1"))],
        checksum="y", ts=datetime.now(timezone.utc),
    )
    await pe.reconcile_resting_orders("ETH/AUD")
    sb = get_supabase()
    row = sb.schema(SCHEMA).table("paper_orders").select("*").eq("id", res.order_id).execute().data[0]
    assert row["status"] == "filled"
    fills = sb.schema(SCHEMA).table("paper_fills").select("*").eq("order_id", res.order_id).execute().data
    # Resting limit that gets crossed by the book is MAKER (we provided liquidity).
    assert all(f["fee_role"] == "maker" for f in fills)
