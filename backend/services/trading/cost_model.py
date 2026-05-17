"""Token → AUD cost calculation.

Spec §7.4. Stores actual cost at the time of the call so historical
attribution is stable even when model prices change later.

Prices are USD per 1M tokens. Edit when Anthropic publishes updates;
defaults below are illustrative — implementer should verify against
docs.anthropic.com/en/docs/about-claude/models at integration time.
"""
from __future__ import annotations

import logging
from decimal import Decimal


logger = logging.getLogger(__name__)


# USD per 1M tokens — input/output.
MODEL_PRICES_USD_PER_M: dict[str, tuple[Decimal, Decimal]] = {
    "claude-opus-4-7":   (Decimal("15"),   Decimal("75")),
    "claude-sonnet-4-6": (Decimal("3"),    Decimal("15")),
    "claude-haiku-4-5":  (Decimal("0.80"), Decimal("4")),
}


def aud_per_usd() -> Decimal:
    """Reuse the same FX source the portfolio dashboard already uses.

    If no shared helper exists, default to 1.5 (the agent decision row
    is annotated with the rate used).
    """
    try:
        from backend.services.portfolio_service import get_aud_usd_rate
        return Decimal(str(get_aud_usd_rate()))
    except Exception:
        return Decimal("1.50")


def compute_cost_aud(
    *,
    model: str, input_tokens: int, output_tokens: int,
    aud_per_usd: Decimal,
) -> Decimal:
    if model in MODEL_PRICES_USD_PER_M:
        in_price, out_price = MODEL_PRICES_USD_PER_M[model]
    else:
        # Conservative fallback: price unknown models at Sonnet 4.6 rates so
        # spend is always recorded (high estimate, never silent zero). The
        # previous default-to-zero hid real cost; the user lost USD 5 of
        # credit while the cost ledger reported pennies. Loud warning so
        # the operator notices the missing price entry.
        in_price, out_price = MODEL_PRICES_USD_PER_M["claude-sonnet-4-6"]
        logger.warning(
            "Unknown model %s — estimating cost at claude-sonnet-4-6 rates "
            "(probable over-estimate; add the real prices to "
            "MODEL_PRICES_USD_PER_M to fix attribution)", model,
        )
    usd_cost = (Decimal(input_tokens) * in_price
                + Decimal(output_tokens) * out_price) / Decimal(1_000_000)
    return (usd_cost * aud_per_usd).quantize(Decimal("0.0001"))
