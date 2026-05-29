from decimal import Decimal

import pytest

import backend.scripts.reset_paper_experiment as reset
from backend.db.supabase_client import get_supabase
from backend.repositories import paper_equity_repo

SCHEMA = "test"
_SENTINEL = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def _dirty(monkeypatch):
    # Patch the Kraken price fetches so the reset is offline/deterministic.
    monkeypatch.setattr(
        "backend.scripts.reset_paper_experiment.fetch_last_prices",
        lambda pairs: {p: Decimal("100") for p in pairs},
    )
    monkeypatch.setattr(
        "backend.scripts.reset_paper_experiment.fetch_btc_aud_price",
        lambda: Decimal("150000"),
    )
    sb = get_supabase()
    # Leave some junk behind to prove it's cleared.
    sb.schema(SCHEMA).table("paper_benchmarks").insert({
        "benchmark_key": "btc_hodl", "ts": "2026-01-01T00:00:00+00:00",
        "equity_aud": "999"}).execute()
    yield


def test_reset_clears_and_reseeds_five_strategies_with_fresh_cash(_dirty):
    reset.reset_paper_experiment(schema=SCHEMA, confirmed=True)
    sb = get_supabase()
    strats = sb.schema(SCHEMA).table("strategies").select("*").execute().data
    names = {s["name"] for s in strats}
    assert {"DCA-Baseline", "Trend-Follower", "Mean-Reverter",
            "Trend-Rule", "Mean-Reversion-Rule"} <= names
    # Each strategy has exactly $1000 cash and nothing else.
    for s in strats:
        pos = (sb.schema(SCHEMA).table("paper_positions").select("*")
               .eq("strategy_id", s["id"]).execute().data)
        assert len(pos) == 1 and pos[0]["asset"] == "AUD"
        assert Decimal(str(pos[0]["qty"])) == Decimal("1000")
    # Old benchmark rows cleared.
    assert paper_equity_repo.list_benchmark_curve("btc_hodl", schema=SCHEMA) == []
    # Benchmark state recorded with all reference prices.
    state = paper_equity_repo.get_benchmark_state(key="experiment", schema=SCHEMA)
    assert state is not None
    for p in ("BTC/AUD", "ETH/AUD", "SOL/AUD", "LINK/AUD", "ADA/AUD"):
        assert p in state["prices_jsonb"]


def test_reset_refuses_without_confirmation(_dirty):
    with pytest.raises(SystemExit):
        reset.reset_paper_experiment(schema=SCHEMA, confirmed=False)
