from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from backend.db.supabase_client import get_supabase
from backend.services.trading.executor import PaperExecutor
from backend.services.trading.price_feed import PriceFeed

SCHEMA = "test"
_SENTINEL = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def _clean():
    sb = get_supabase()
    for t in ("paper_fills", "paper_orders", "agent_decisions"):
        sb.schema(SCHEMA).table(t).delete().neq("id", _SENTINEL).execute()
    sb.schema(SCHEMA).table("paper_positions").delete().neq("strategy_id", _SENTINEL).execute()
    sb.schema(SCHEMA).table("strategies").delete().neq("id", _SENTINEL).execute()
    yield


@pytest.mark.asyncio
async def test_book_update_fills_a_resting_limit_order(_clean):
    sb = get_supabase()
    # Seed a strategy with cash.
    sid = sb.schema(SCHEMA).table("strategies").insert({
        "name": "rec", "execution_mode": "deterministic",
        "deterministic_config": {"cadence_cron": "0 9 * * 1",
                                 "allocations": {"ETH/AUD": "1.0"}},
        "starting_balance_aud": "1000",
        "risk_caps": {"max_single_asset_pct": 100, "max_total_crypto_exposure_pct": 100,
                      "max_order_aud": 250, "daily_loss_cap_aud": 1000000,
                      "max_drawdown_pct_before_pause": 100,
                      "allowed_pairs": ["ETH/AUD"]},
        "kill_criteria": {"auto_pause_when": []},
        "status": "active", "dry_run": False,
    }).execute().data[0]["id"]
    sb.schema(SCHEMA).table("paper_positions").insert({
        "strategy_id": sid, "asset": "AUD", "qty": "1000",
        "avg_cost_aud": "1", "lots_jsonb": []}).execute()

    executor = PaperExecutor(schema=SCHEMA)
    feed = PriceFeed(pairs=["ETH/AUD"], executor=executor)

    # A book where ETH asks sit ABOVE our limit → resting (no immediate fill).
    high = {"channel": "book", "type": "snapshot", "data": [{
        "symbol": "ETH/AUD",
        "asks": [{"price": "3100", "qty": "1"}],
        "bids": [{"price": "3090", "qty": "1"}],
        "checksum": "1", "timestamp": datetime.now(timezone.utc).isoformat()}]}
    await feed._handle(high)
    # qty*limit = 0.05*3000 = 150 AUD, under the uniform 250 per-order cap, so
    # the order isn't rejected on risk grounds — it rests (asks 3100 > 3000).
    res = await executor.submit_order(
        strategy_id=uuid4().__class__(sid), idempotency_key="k1",
        pair="ETH/AUD", side="buy", type="limit", qty=Decimal("0.05"),
        limit_price=Decimal("3000"))
    assert res.status == "pending"

    # Market drops so an ask now crosses our 3000 limit → next book update fills it.
    low = {"channel": "book", "type": "snapshot", "data": [{
        "symbol": "ETH/AUD",
        "asks": [{"price": "2990", "qty": "1"}],
        "bids": [{"price": "2980", "qty": "1"}],
        "checksum": "2", "timestamp": datetime.now(timezone.utc).isoformat()}]}
    await feed._handle(low)

    order = sb.schema(SCHEMA).table("paper_orders").select("*").eq("id", res.order_id).execute().data[0]
    assert order["status"] == "filled"
