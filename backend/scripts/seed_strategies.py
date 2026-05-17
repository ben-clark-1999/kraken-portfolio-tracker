"""Seed the three v1 strategies. Idempotent by name.

Run on app boot via main.py (after migrations) AND from CLI:
    backend/.venv/bin/python -m backend.scripts.seed_strategies
"""
from __future__ import annotations

import logging
from decimal import Decimal

from backend.db.supabase_client import get_supabase


logger = logging.getLogger(__name__)


_RISK_CAPS_DEFAULT = {
    "max_single_asset_pct": 30,
    "max_total_crypto_exposure_pct": 60,
    "max_order_aud": 250,
    "daily_loss_cap_aud": 100,
    "max_drawdown_pct_before_pause": 25,
    "allowed_pairs": ["ETH/AUD", "LINK/AUD", "ADA/AUD", "SOL/AUD"],
}

_KILL_CRITERIA_DEFAULT = {
    "auto_pause_when": [
        {"metric": "drawdown_pct", "op": ">=", "value": 25.0},
        {"metric": "daily_loss_aud", "op": ">=", "value": 100.0},
    ],
}


def _existing_id_by_name(name: str, schema: str) -> str | None:
    sb = get_supabase()
    r = (sb.schema(schema).table("strategies").select("id")
           .eq("name", name).limit(1).execute())
    return r.data[0]["id"] if r.data else None


def _seed_cash(strategy_id: str, amount_aud: Decimal, schema: str) -> None:
    sb = get_supabase()
    r = (sb.schema(schema).table("paper_positions").select("strategy_id")
           .eq("strategy_id", strategy_id).eq("asset", "AUD")
           .limit(1).execute())
    if r.data:
        return
    sb.schema(schema).table("paper_positions").insert({
        "strategy_id": strategy_id,
        "asset": "AUD",
        "qty": str(amount_aud),
        "avg_cost_aud": "1",
        "lots_jsonb": [],
    }).execute()


def seed_dca_baseline(*, schema: str = "public") -> str:
    existing = _existing_id_by_name("DCA-Baseline", schema)
    if existing:
        return existing
    sb = get_supabase()
    payload = {
        "name": "DCA-Baseline",
        "description": "Deterministic fortnightly buy; ETH-tilted control benchmark.",
        "execution_mode": "deterministic",
        "deterministic_config": {
            "cadence_cron": "0 9 */14 * *",
            "tz": "Australia/Sydney",
            "allocations": {
                "ETH/AUD": "0.50",
                "SOL/AUD": "0.25",
                "LINK/AUD": "0.15",
                "ADA/AUD": "0.10",
            },
        },
        "starting_balance_aud": "1000",
        "trigger_config": {
            "triggers": [{"type": "cron", "expr": "0 9 */14 * *",
                          "tz": "Australia/Sydney"}],
            "debounce_seconds": 0,
            "cooldown_seconds": 0,
            "max_calls_per_hour": 1000,
        },
        "risk_caps": _RISK_CAPS_DEFAULT,
        "kill_criteria": _KILL_CRITERIA_DEFAULT,
        "status": "active",
        "dry_run": False,
    }
    sid = sb.schema(schema).table("strategies").insert(payload).execute().data[0]["id"]
    _seed_cash(sid, Decimal("1000"), schema)
    logger.info("Seeded strategy DCA-Baseline (%s)", sid)
    return sid


def _seed_llm_strategy(
    *, name: str, persona_key: str,
    triggers_extra: list[dict], schema: str,
) -> str:
    existing = _existing_id_by_name(name, schema)
    if existing:
        return existing
    sb = get_supabase()
    payload = {
        "name": name,
        "execution_mode": "llm_agent",
        "persona_key": persona_key,
        "starting_balance_aud": "1000",
        "trigger_config": {
            "triggers": [
                # 12-hourly heartbeat keeps LLM cost down. Event-driven
                # triggers (breakouts / stretches / fills) still fire as
                # before for actual signals.
                {"type": "interval", "minutes": 720},
                *triggers_extra,
                {"type": "order_filled"},
            ],
            "debounce_seconds": 5,
            "cooldown_seconds": 900,
            "max_calls_per_hour": 10,
        },
        "risk_caps": _RISK_CAPS_DEFAULT,
        "kill_criteria": _KILL_CRITERIA_DEFAULT,
        "status": "active",
        "dry_run": False,
        # Haiku 4.5 — ~4x cheaper than Sonnet per token. Acceptable quality
        # for paper-trading at v1 stakes; revisit if/when behaviour shows
        # the model is missing nuance the larger model would catch.
        "model_preference": "claude-haiku-4-5",
    }
    sid = sb.schema(schema).table("strategies").insert(payload).execute().data[0]["id"]
    _seed_cash(sid, Decimal("1000"), schema)
    logger.info("Seeded strategy %s (%s)", name, sid)
    return sid


def seed_trend_follower(*, schema: str = "public") -> str:
    return _seed_llm_strategy(
        name="Trend-Follower",
        persona_key="trend-follower",
        triggers_extra=[
            {"type": "price_breakout", "pair": p, "lookback_bars": 24,
             "interval": "1h", "min_move_pct": 1.5}
            for p in ("ETH/AUD", "LINK/AUD", "ADA/AUD", "SOL/AUD")
        ],
        schema=schema,
    )


def seed_mean_reverter(*, schema: str = "public") -> str:
    return _seed_llm_strategy(
        name="Mean-Reverter",
        persona_key="mean-reverter",
        triggers_extra=[
            {"type": "price_stretch", "pair": p, "lookback_bars": 48,
             "interval": "1h", "stdev": 2.0}
            for p in ("ETH/AUD", "LINK/AUD", "ADA/AUD", "SOL/AUD")
        ],
        schema=schema,
    )


def seed_all(*, schema: str = "public") -> None:
    seed_dca_baseline(schema=schema)
    seed_trend_follower(schema=schema)
    seed_mean_reverter(schema=schema)


if __name__ == "__main__":
    seed_all()
    print("Seeded 3 strategies.")
