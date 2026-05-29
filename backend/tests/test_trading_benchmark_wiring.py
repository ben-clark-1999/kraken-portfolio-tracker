from datetime import datetime, timezone
from decimal import Decimal

import pytest

import backend.services.trading.benchmark_snapshot as bs
from backend.db.supabase_client import get_supabase
from backend.repositories import paper_equity_repo

SCHEMA = "test"


@pytest.fixture
def _clean():
    sb = get_supabase()
    sb.schema(SCHEMA).table("paper_benchmarks").delete().neq(
        "benchmark_key", "__sentinel__").execute()
    sb.schema(SCHEMA).table("paper_benchmark_state").delete().neq(
        "benchmark_key", "__sentinel__").execute()
    yield


def test_snapshot_benchmarks_writes_both_curves(monkeypatch, _clean):
    t0 = datetime(2026, 5, 29, 0, 0, tzinfo=timezone.utc)
    paper_equity_repo.set_benchmark_state(
        key="experiment", t0=t0,
        prices={"BTC/AUD": Decimal("100000"),
                "ETH/AUD": Decimal("3000"), "SOL/AUD": Decimal("100"),
                "LINK/AUD": Decimal("15"), "ADA/AUD": Decimal("0.40")},
        schema=SCHEMA,
    )
    # BTC doubled since t0 → btc_hodl should be 2000.
    monkeypatch.setattr(bs, "fetch_btc_aud_price", lambda: Decimal("200000"))
    # Alts unchanged → alt basket stays at 1000.
    alt_mids = {"ETH/AUD": Decimal("3000"), "SOL/AUD": Decimal("100"),
                "LINK/AUD": Decimal("15"), "ADA/AUD": Decimal("0.40")}

    bs.snapshot_benchmarks(alt_mids=alt_mids, schema=SCHEMA)

    btc = paper_equity_repo.list_benchmark_curve("btc_hodl", schema=SCHEMA)
    alt = paper_equity_repo.list_benchmark_curve("alt_basket_equal_weight", schema=SCHEMA)
    assert btc and Decimal(btc[-1]["equity_aud"]) == Decimal("2000.0000")
    assert alt and Decimal(alt[-1]["equity_aud"]) == Decimal("1000.0000")


def test_snapshot_benchmarks_noop_without_state(monkeypatch, _clean):
    monkeypatch.setattr(bs, "fetch_btc_aud_price", lambda: Decimal("200000"))
    bs.snapshot_benchmarks(alt_mids={}, schema=SCHEMA)  # no state recorded
    assert paper_equity_repo.list_benchmark_curve("btc_hodl", schema=SCHEMA) == []
