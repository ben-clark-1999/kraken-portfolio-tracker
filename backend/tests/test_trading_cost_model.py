from decimal import Decimal

from backend.services.trading.cost_model import (
    compute_cost_aud, MODEL_PRICES_USD_PER_M,
)


def test_known_model_price_is_present():
    assert "claude-sonnet-4-6" in MODEL_PRICES_USD_PER_M
    assert "claude-haiku-4-5" in MODEL_PRICES_USD_PER_M


def test_compute_cost_aud_for_sonnet_call():
    # 5,000 input tokens, 1,000 output tokens at Sonnet 4.6 (illustrative
    # prices: $3/M input, $15/M output → USD 0.03; at AUD/USD 1.5 → AUD 0.045)
    cost = compute_cost_aud(
        model="claude-sonnet-4-6",
        input_tokens=5_000, output_tokens=1_000,
        aud_per_usd=Decimal("1.50"),
    )
    assert cost > Decimal("0")
    assert cost < Decimal("0.50")   # sanity bound


def test_unknown_model_estimates_at_sonnet_rates_with_warning(caplog):
    # Per the post-mortem on 2026-05-17 (USD 5 of credit silently burned
    # while the ledger reported $0), unknown models must NEVER report zero
    # cost. Conservative fallback is claude-sonnet-4-6 pricing.
    import logging
    caplog.set_level(logging.WARNING)
    cost = compute_cost_aud(model="unknown-model-x",
                            input_tokens=1000, output_tokens=100,
                            aud_per_usd=Decimal("1.50"))
    sonnet_reference = compute_cost_aud(model="claude-sonnet-4-6",
                                        input_tokens=1000, output_tokens=100,
                                        aud_per_usd=Decimal("1.50"))
    assert cost > Decimal("0"), "unknown model must not silently report $0 cost"
    assert cost == sonnet_reference, "unknown model should price at Sonnet 4.6"
    assert any("Unknown model" in r.message for r in caplog.records), \
        "should log a warning when falling back"
