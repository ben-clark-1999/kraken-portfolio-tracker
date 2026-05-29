"""Benchmark equity curves: BTC HODL and equal-weight alt basket.

Spec §4.7 + §8.3 — equal-weight basket REBALANCES monthly on the 1st
so that "lucky drift" doesn't make the benchmark unfairly hard to beat.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

import httpx


def compute_btc_hodl_equity(
    *, starting_balance_aud: Decimal,
    btc_price_at_start: Decimal, btc_price_now: Decimal,
) -> Decimal:
    if btc_price_at_start == 0:
        return Decimal("0")
    units = starting_balance_aud / btc_price_at_start
    return (units * btc_price_now).quantize(Decimal("0.0001"))


@dataclass
class AltBasketState:
    units: dict[str, Decimal] = field(default_factory=dict)
    last_rebalance_at: datetime | None = None

    @classmethod
    def initialise(
        cls, *, starting_balance_aud: Decimal,
        initial_prices: dict[str, Decimal], t0: datetime,
    ) -> "AltBasketState":
        per_asset = starting_balance_aud / Decimal(len(initial_prices))
        units = {pair: (per_asset / price) for pair, price in initial_prices.items()}
        return cls(units=units, last_rebalance_at=t0)

    def equity(self, *, current_prices: dict[str, Decimal]) -> Decimal:
        return sum(
            (self.units.get(p, Decimal("0")) * current_prices.get(p, Decimal("0"))
             for p in self.units),
            Decimal("0"),
        )

    def rebalance(self, *, current_prices: dict[str, Decimal],
                  now: datetime) -> None:
        eq = self.equity(current_prices=current_prices)
        per_asset = eq / Decimal(len(self.units))
        self.units = {p: (per_asset / current_prices[p]) for p in self.units}
        self.last_rebalance_at = now


def compute_alt_basket_equity(
    *, state: AltBasketState, current_prices: dict[str, Decimal],
) -> Decimal:
    return state.equity(current_prices=current_prices).quantize(Decimal("0.0001"))


def next_rebalance_due_at(last: datetime) -> datetime:
    # First of next month at 00:00 UTC.
    year, month = last.year, last.month
    if month == 12:
        year, month = year + 1, 1
    else:
        month += 1
    return datetime(year, month, 1, 0, 0, tzinfo=timezone.utc)


logger = logging.getLogger(__name__)

# Kraken's BTC/AUD pair. BTC is not in the trading universe or WS feed — it's a
# price reference only, fetched from the public REST ticker each hourly run.
_BTC_TICKER_URL = "https://api.kraken.com/0/public/Ticker?pair=XBTAUD"
_ALT_PAIRS = ["ETH/AUD", "SOL/AUD", "LINK/AUD", "ADA/AUD"]


def fetch_btc_aud_price() -> Decimal:
    """Last-trade BTC/AUD from Kraken's public REST ticker.

    Reads the single returned result entry's last-trade price regardless of
    the response key (Kraken may return XXBTZAUD / XBTAUD).
    """
    r = httpx.get(_BTC_TICKER_URL, timeout=10)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"Kraken Ticker error: {data['error']}")
    result = data["result"]
    entry = next(iter(result.values()))
    return Decimal(str(entry["c"][0]))


def snapshot_benchmarks(*, alt_mids: dict[str, Decimal], schema: str = "public",
                        now: datetime | None = None) -> None:
    """Write btc_hodl + alt_basket_equal_weight snapshots (spec §3.4).

    Both are buy-and-hold from t0. The alt basket re-derives its fixed units
    from the recorded t0 prices every run (no rebalance — spec decision).
    No-op until the reset script has recorded the benchmark state.
    """
    from backend.repositories import paper_equity_repo

    state = paper_equity_repo.get_benchmark_state(key="experiment", schema=schema)
    if state is None:
        return
    ts = now or datetime.now(timezone.utc)
    t0_prices = {k: Decimal(str(v)) for k, v in (state.get("prices_jsonb") or {}).items()}
    t0 = datetime.fromisoformat(state["t0"].replace("Z", "+00:00"))
    starting = Decimal("1000")

    # BTC HODL.
    try:
        btc_now = fetch_btc_aud_price()
        btc_eq = compute_btc_hodl_equity(
            starting_balance_aud=starting,
            btc_price_at_start=t0_prices["BTC/AUD"],
            btc_price_now=btc_now,
        )
        paper_equity_repo.insert_benchmark_snapshot(
            benchmark_key="btc_hodl", ts=ts, equity_aud=btc_eq, schema=schema)
    except Exception:
        logger.exception("[Benchmark] btc_hodl snapshot failed")

    # Equal-weight alt basket (buy-and-hold, units fixed at t0).
    try:
        alt_t0 = {p: t0_prices[p] for p in _ALT_PAIRS if p in t0_prices}
        current = {p: alt_mids[p] for p in alt_t0 if p in alt_mids}
        if len(current) == len(alt_t0) and alt_t0:
            basket = AltBasketState.initialise(
                starting_balance_aud=starting, initial_prices=alt_t0, t0=t0)
            alt_eq = compute_alt_basket_equity(state=basket, current_prices=current)
            paper_equity_repo.insert_benchmark_snapshot(
                benchmark_key="alt_basket_equal_weight", ts=ts,
                equity_aud=alt_eq, schema=schema)
        else:
            logger.warning("[Benchmark] alt basket: missing current prices, skipped")
    except Exception:
        logger.exception("[Benchmark] alt_basket snapshot failed")
