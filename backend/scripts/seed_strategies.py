"""Seed the three v1 strategies. Idempotent by name.

Run on app boot via main.py (after migrations) AND from CLI:
    backend/.venv/bin/python -m backend.scripts.seed_strategies
"""
from __future__ import annotations

import logging
from decimal import Decimal

from backend.db.supabase_client import get_supabase


logger = logging.getLogger(__name__)


# Level playing field (spec §3.6): identical rules for every strategy. No
# allocation limits and no auto-pause — handicapping the active strategies
# with risk limits the DCA baseline doesn't have would test our risk rules,
# not the method. The per-order cap stays as uniform execution realism
# (reachable via order-splitting). daily_loss/drawdown are set out of reach
# so the kill machinery (kept for future real-money use) cannot fire here.
_RISK_CAPS_DEFAULT = {
    "max_single_asset_pct": 100,
    "max_total_crypto_exposure_pct": 100,
    "max_order_aud": 250,
    "daily_loss_cap_aud": 1_000_000,
    "max_drawdown_pct_before_pause": 100,
    "allowed_pairs": ["ETH/AUD", "LINK/AUD", "ADA/AUD", "SOL/AUD"],
}

_KILL_CRITERIA_DEFAULT = {
    "auto_pause_when": [],
}

# Weekly DCA cadence. Use the day NAME ('tue'), not the number: APScheduler's
# CronTrigger.from_crontab reads numeric day-of-week as 0=Mon..6=Sun, so the
# standard-cron '... * * 2' (intended Tuesday) silently fires on Wednesday. The
# name is unambiguous across both conventions.
# Anchored to Tuesdays: the live experiment was kicked off on Tue 2026-06-02
# (see scripts/start_dca_today.py), so the recurring slice fires on the same
# weekday it started, keeping the baseline cadence regular.
DCA_CADENCE_CRON = "0 9 * * tue"


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
        "description": "Fixed-slice weekly DCA (12 buys); ETH-tilted passive baseline.",
        "execution_mode": "deterministic",
        "deterministic_config": {
            "cadence_cron": DCA_CADENCE_CRON,  # Tuesdays 09:00 Australia/Sydney
            "tz": "Australia/Sydney",
            "mode": "dca",
            "num_buys": 12,                 # ≈ 3 months of weekly slices
            "allocations": {
                "ETH/AUD": "0.50",
                "SOL/AUD": "0.25",
                "LINK/AUD": "0.15",
                "ADA/AUD": "0.10",
            },
        },
        "starting_balance_aud": "1000",
        "trigger_config": {
            "triggers": [{"type": "cron", "expr": DCA_CADENCE_CRON,
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


def _seed_deterministic_rule(
    *, name: str, description: str, det_config: dict, schema: str,
) -> str:
    existing = _existing_id_by_name(name, schema)
    if existing:
        return existing
    sb = get_supabase()
    payload = {
        "name": name,
        "description": description,
        "execution_mode": "deterministic",
        "deterministic_config": det_config,
        "starting_balance_aud": "1000",
        "trigger_config": {
            "triggers": [{"type": "cron", "expr": det_config["cadence_cron"],
                          "tz": det_config.get("tz", "Australia/Sydney")}],
            "debounce_seconds": 0, "cooldown_seconds": 0, "max_calls_per_hour": 1000,
        },
        "risk_caps": _RISK_CAPS_DEFAULT,
        "kill_criteria": _KILL_CRITERIA_DEFAULT,
        "status": "active",
        "dry_run": False,
    }
    sid = sb.schema(schema).table("strategies").insert(payload).execute().data[0]["id"]
    _seed_cash(sid, Decimal("1000"), schema)
    logger.info("Seeded strategy %s (%s)", name, sid)
    return sid


def seed_trend_rule(*, schema: str = "public") -> str:
    return _seed_deterministic_rule(
        name="Trend-Rule",
        description="Deterministic twin of Trend-Follower: 24h breakout ±1.5%.",
        det_config={
            "cadence_cron": "0 9 * * *", "tz": "Australia/Sydney",
            "mode": "trend_rule",
            "universe": ["ETH/AUD", "SOL/AUD", "LINK/AUD", "ADA/AUD"],
            "min_move_pct": "1.5",
        },
        schema=schema,
    )


def seed_mean_reversion_rule(*, schema: str = "public") -> str:
    return _seed_deterministic_rule(
        name="Mean-Reversion-Rule",
        description="Deterministic twin of Mean-Reverter: 48h z-score, buy ≤-2σ, exit ≥mean.",
        det_config={
            "cadence_cron": "0 9 * * *", "tz": "Australia/Sydney",
            "mode": "mean_reversion_rule",
            "universe": ["ETH/AUD", "SOL/AUD", "LINK/AUD", "ADA/AUD"],
            "entry_z": "-2", "exit_z": "0",
        },
        schema=schema,
    )


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
                # Daily 09:00 cron, matched to the deterministic rule twins
                # (Trend-Rule / Mean-Reversion-Rule) so the LLM and its twin
                # wake at the same time on the same data — the comparison is
                # then about reasoning, not cadence. NOTE: the event-driven
                # breakout/stretch/order_filled triggers below are configured
                # but not yet wired to a publisher (see trigger_evaluators),
                # so today they don't fire — the daily cron is the live wake.
                {"type": "cron", "expr": "0 9 * * *", "tz": "Australia/Sydney"},
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
    seed_trend_rule(schema=schema)
    seed_mean_reversion_rule(schema=schema)


if __name__ == "__main__":
    seed_all()
    print("Seeded 5 strategies.")
