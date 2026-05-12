from decimal import Decimal
from datetime import datetime, timezone

from backend.models.trading import (
    OrderBookLevel, OrderBookSnapshot,
    Fill, OrderResult, OrderRow,
    TickEvent, BookUpdateEvent, TriggerEvent,
    RiskCaps, KillCriteria, DeterministicConfig,
)


def test_order_book_level_construction():
    level = OrderBookLevel(price=Decimal("25.00"), qty=Decimal("20"))
    assert level.price == Decimal("25.00")


def test_order_book_snapshot_sorted_invariant():
    snap = OrderBookSnapshot(
        pair="ETH/AUD",
        asks=[
            OrderBookLevel(price=Decimal("3196.50"), qty=Decimal("0.5")),
            OrderBookLevel(price=Decimal("3196.60"), qty=Decimal("1.0")),
        ],
        bids=[
            OrderBookLevel(price=Decimal("3196.40"), qty=Decimal("0.8")),
            OrderBookLevel(price=Decimal("3196.30"), qty=Decimal("1.2")),
        ],
        checksum="abc123",
        ts=datetime.now(timezone.utc),
    )
    # asks ascending, bids descending — assert top of book
    assert snap.asks[0].price < snap.asks[1].price
    assert snap.bids[0].price > snap.bids[1].price


def test_order_result_serialises_fills():
    res = OrderResult(
        order_id="00000000-0000-0000-0000-000000000001",
        status="filled",
        fills=[Fill(qty=Decimal("0.1"), price=Decimal("3196.60"),
                    fee_aud=Decimal("1.28"), fee_role="taker",
                    book_state_hash="h1",
                    filled_at=datetime.now(timezone.utc))],
        reject_reason=None,
    )
    assert res.status == "filled"
    assert len(res.fills) == 1


def test_risk_caps_defaults():
    caps = RiskCaps()
    assert caps.max_single_asset_pct == Decimal("30")
    assert caps.max_total_crypto_exposure_pct == Decimal("60")
    assert caps.max_order_aud == Decimal("250")
    assert caps.daily_loss_cap_aud == Decimal("100")
    assert caps.max_drawdown_pct_before_pause == Decimal("25")
    assert caps.allowed_pairs == ["ETH/AUD", "LINK/AUD", "ADA/AUD", "SOL/AUD"]


def test_trigger_event_discriminated_by_type():
    from backend.models.trading import validate_trigger_event, CronTriggerEvent, IntervalTriggerEvent

    interval = validate_trigger_event(
        {"type": "interval", "minutes": 60, "ts": "2026-05-12T00:00:00Z"}
    )
    assert isinstance(interval, IntervalTriggerEvent)
    assert interval.minutes == 60

    cron = validate_trigger_event(
        {"type": "cron", "expr": "0 9 * * *", "ts": "2026-05-12T00:00:00Z"}
    )
    assert isinstance(cron, CronTriggerEvent)
    assert cron.expr == "0 9 * * *"

    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        validate_trigger_event(
            {"type": "unknown_event_kind", "ts": "2026-05-12T00:00:00Z"}
        )


def test_deterministic_config_weights_sum_to_one():
    cfg = DeterministicConfig(
        cadence_cron="0 9 */14 * *", tz="Australia/Sydney",
        allocations={"ETH/AUD": Decimal("0.50"),
                     "SOL/AUD": Decimal("0.25"),
                     "LINK/AUD": Decimal("0.15"),
                     "ADA/AUD": Decimal("0.10")},
    )
    assert sum(cfg.allocations.values()) == Decimal("1.00")
