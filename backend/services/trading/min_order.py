"""Minimum-order runtime validation against Kraken's AssetPairs.

Spec §5.7 rule: at strategy startup, drop any pair where
ordermin × current_price > 5% of max position.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable
import logging

import httpx

logger = logging.getLogger(__name__)


THRESHOLD_FRACTION = Decimal("0.05")
KRAKEN_BASE = "https://api.kraken.com/0/public"


# ── Kraken REST fetchers (patchable in tests) ───────────────────

def _to_kraken_pair(pair: str) -> str:
    # "ETH/AUD" → "ETHAUD". (Kraken accepts both the legacy XBT… form and
    # the ISO form for query input; the response key may differ.)
    return pair.replace("/", "")


def fetch_asset_pairs(pairs: Iterable[str]) -> dict[str, dict[str, Decimal]]:
    kraken_codes = ",".join(_to_kraken_pair(p) for p in pairs)
    url = f"{KRAKEN_BASE}/AssetPairs?pair={kraken_codes}"
    r = httpx.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"Kraken AssetPairs error: {data['error']}")
    result: dict[str, dict[str, Decimal]] = {}
    response_pairs = data["result"]
    # Map the response back to our canonical pair names.
    for canonical in pairs:
        entry = None
        target = _to_kraken_pair(canonical)
        for key, val in response_pairs.items():
            if key == target or val.get("wsname") == canonical:
                entry = val
                break
        if entry is None:
            logger.warning("Kraken did not return data for %s", canonical)
            continue
        result[canonical] = {
            "ordermin": Decimal(str(entry["ordermin"])),
            "costmin": Decimal(str(entry.get("costmin", "0") or "0")),
        }
    return result


def fetch_last_prices(pairs: Iterable[str]) -> dict[str, Decimal]:
    kraken_codes = ",".join(_to_kraken_pair(p) for p in pairs)
    url = f"{KRAKEN_BASE}/Ticker?pair={kraken_codes}"
    r = httpx.get(url, timeout=10)
    r.raise_for_status()
    data = r.json()
    if data.get("error"):
        raise RuntimeError(f"Kraken Ticker error: {data['error']}")
    result: dict[str, Decimal] = {}
    response_pairs = data["result"]
    for canonical in pairs:
        entry = None
        target = _to_kraken_pair(canonical)
        for key, val in response_pairs.items():
            if key == target:
                entry = val
                break
        if entry is None:
            continue
        result[canonical] = Decimal(str(entry["c"][0]))
    return result


# ── Decision logic ──────────────────────────────────────────────

@dataclass
class MinOrderDecision:
    pair: str
    passes: bool
    min_order_aud: Decimal
    threshold_aud: Decimal
    reason: str | None = None


def min_notional_aud(*, ordermin: Decimal, costmin: Decimal, price: Decimal) -> Decimal:
    """Per-order AUD floor enforcing BOTH Kraken minimums.

    `ordermin` is a base-asset quantity (e.g. ETH); converted to AUD at
    `price`. `costmin` is already an AUD minimum cost. An order must clear
    the larger of the two, so we return their max.
    """
    return max(ordermin * price, costmin)


def evaluate_min_order_for_pair(
    *,
    pair: str,
    ordermin: Decimal,
    current_price: Decimal,
    max_position_aud: Decimal,
) -> MinOrderDecision:
    min_order_aud = ordermin * current_price
    threshold = max_position_aud * THRESHOLD_FRACTION
    if min_order_aud > threshold:
        return MinOrderDecision(
            pair=pair, passes=False,
            min_order_aud=min_order_aud, threshold_aud=threshold,
            reason=f"min order AUD {min_order_aud} exceeds threshold AUD {threshold}",
        )
    return MinOrderDecision(
        pair=pair, passes=True,
        min_order_aud=min_order_aud, threshold_aud=threshold,
    )


def filter_allowed_pairs_by_min_order(
    *, pairs: list[str], max_position_aud: Decimal,
) -> tuple[list[str], list[str]]:
    """Returns (kept, dropped). Fetches live Kraken data."""
    if not pairs:
        return [], []
    asset_pairs = fetch_asset_pairs(pairs)
    prices = fetch_last_prices(pairs)
    kept: list[str] = []
    dropped: list[str] = []
    for pair in pairs:
        if pair not in asset_pairs or pair not in prices:
            logger.warning("Skipping %s — missing Kraken data", pair)
            dropped.append(pair)
            continue
        decision = evaluate_min_order_for_pair(
            pair=pair,
            ordermin=asset_pairs[pair]["ordermin"],
            current_price=prices[pair],
            max_position_aud=max_position_aud,
        )
        if decision.passes:
            kept.append(pair)
        else:
            dropped.append(pair)
            logger.warning("Min-order check dropped %s: %s", pair, decision.reason)
    return kept, dropped
