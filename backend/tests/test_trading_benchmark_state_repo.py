from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.db.supabase_client import get_supabase
from backend.repositories import paper_equity_repo

SCHEMA = "test"


@pytest.fixture
def _clean():
    sb = get_supabase()
    sb.schema(SCHEMA).table("paper_benchmark_state").delete().neq(
        "benchmark_key", "__sentinel__").execute()
    yield


def test_set_then_get_roundtrips_t0_and_prices(_clean):
    t0 = datetime(2026, 5, 29, 0, 0, tzinfo=timezone.utc)
    paper_equity_repo.set_benchmark_state(
        key="experiment", t0=t0,
        prices={"BTC/AUD": Decimal("150000"), "ETH/AUD": Decimal("3000")},
        schema=SCHEMA,
    )
    state = paper_equity_repo.get_benchmark_state(key="experiment", schema=SCHEMA)
    assert state is not None
    assert state["prices_jsonb"]["BTC/AUD"] == "150000"
    assert state["t0"].startswith("2026-05-29")


def test_get_missing_returns_none(_clean):
    assert paper_equity_repo.get_benchmark_state(key="nope", schema=SCHEMA) is None
