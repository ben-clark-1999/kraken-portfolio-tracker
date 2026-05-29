"""Repository for paper_equity_snapshots + paper_benchmarks."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from backend.db.supabase_client import get_supabase


def insert_snapshot(
    *, strategy_id: UUID, ts: datetime, equity_aud: Decimal,
    cash_aud: Decimal, position_value_aud: Decimal,
    realised_pnl_aud: Decimal = Decimal("0"),
    unrealised_pnl_aud: Decimal = Decimal("0"),
    schema: str = "public",
) -> None:
    sb = get_supabase()
    sb.schema(schema).table("paper_equity_snapshots").upsert({
        "strategy_id": str(strategy_id),
        "ts": ts.isoformat(),
        "equity_aud": str(equity_aud),
        "cash_aud": str(cash_aud),
        "position_value_aud": str(position_value_aud),
        "realised_pnl_aud": str(realised_pnl_aud),
        "unrealised_pnl_aud": str(unrealised_pnl_aud),
    }, on_conflict="strategy_id,ts").execute()


def list_curve(
    strategy_id: UUID, *, since: datetime | None = None,
    schema: str = "public",
) -> list[dict]:
    sb = get_supabase()
    q = sb.schema(schema).table("paper_equity_snapshots").select("*").eq("strategy_id", str(strategy_id))
    if since is not None:
        q = q.gte("ts", since.isoformat())
    return (q.order("ts").execute().data or [])


def insert_benchmark_snapshot(
    *, benchmark_key: str, ts: datetime, equity_aud: Decimal,
    schema: str = "public",
) -> None:
    sb = get_supabase()
    sb.schema(schema).table("paper_benchmarks").upsert({
        "benchmark_key": benchmark_key,
        "ts": ts.isoformat(), "equity_aud": str(equity_aud),
    }, on_conflict="benchmark_key,ts").execute()


def list_benchmark_curve(
    benchmark_key: str, *, since: datetime | None = None,
    schema: str = "public",
) -> list[dict]:
    sb = get_supabase()
    q = sb.schema(schema).table("paper_benchmarks").select("*").eq("benchmark_key", benchmark_key)
    if since is not None:
        q = q.gte("ts", since.isoformat())
    return (q.order("ts").execute().data or [])


def set_benchmark_state(
    *, key: str, t0: datetime, prices: dict[str, Decimal],
    schema: str = "public",
) -> None:
    sb = get_supabase()
    sb.schema(schema).table("paper_benchmark_state").upsert({
        "benchmark_key": key,
        "t0": t0.isoformat(),
        "prices_jsonb": {k: str(v) for k, v in prices.items()},
    }, on_conflict="benchmark_key").execute()


def get_benchmark_state(*, key: str, schema: str = "public") -> dict | None:
    sb = get_supabase()
    r = (sb.schema(schema).table("paper_benchmark_state").select("*")
           .eq("benchmark_key", key).limit(1).execute())
    return r.data[0] if r.data else None
