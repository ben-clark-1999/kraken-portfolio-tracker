"""Guarded clean-slate reset of the paper-trading experiment (spec §4).

Deletes all strategy rows (cascading orders/fills/positions/equity/decisions),
clears both benchmark tables, re-seeds the five strategies with the current
config, and records the benchmark t0 + reference prices.

Usage:
    backend/.venv/bin/python -m backend.scripts.reset_paper_experiment --yes
    backend/.venv/bin/python -m backend.scripts.reset_paper_experiment --yes --schema test
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from decimal import Decimal

from backend.db.supabase_client import get_supabase
from backend.repositories import paper_equity_repo
from backend.scripts.seed_strategies import seed_all
from backend.services.trading.benchmark_snapshot import fetch_btc_aud_price
from backend.services.trading.min_order import fetch_last_prices

logger = logging.getLogger(__name__)

_SENTINEL_UUID = "00000000-0000-0000-0000-000000000001"
_REFERENCE_PAIRS = ["ETH/AUD", "SOL/AUD", "LINK/AUD", "ADA/AUD"]


def reset_paper_experiment(*, schema: str = "public", confirmed: bool = False) -> None:
    if not confirmed:
        sys.exit("Refusing to reset without --yes. This deletes ALL paper-trading data.")

    sb = get_supabase()

    # 1. Delete all strategies — FKs cascade to orders, fills, positions,
    #    equity snapshots, and agent_decisions.
    sb.schema(schema).table("strategies").delete().neq("id", _SENTINEL_UUID).execute()
    # 2. Clear benchmark curves + state.
    sb.schema(schema).table("paper_benchmarks").delete().neq(
        "benchmark_key", "__sentinel__").execute()
    sb.schema(schema).table("paper_benchmark_state").delete().neq(
        "benchmark_key", "__sentinel__").execute()

    # 3. Re-seed the five strategies (fresh $1000 cash each) with current config.
    seed_all(schema=schema)

    # 4. Record the benchmark t0 + reference prices (BTC + four alts).
    t0 = datetime.now(timezone.utc)
    prices: dict[str, Decimal] = dict(fetch_last_prices(_REFERENCE_PAIRS))
    prices["BTC/AUD"] = fetch_btc_aud_price()
    paper_equity_repo.set_benchmark_state(key="experiment", t0=t0, prices=prices, schema=schema)

    logger.info("Paper experiment reset: 5 strategies reseeded, benchmark t0=%s", t0.isoformat())


if __name__ == "__main__":
    args = set(sys.argv[1:])
    schema = "public"
    if "--schema" in sys.argv:
        schema = sys.argv[sys.argv.index("--schema") + 1]
    reset_paper_experiment(schema=schema, confirmed=("--yes" in args))
    print("Done.")
