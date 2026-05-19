"""Tests for the pure rendering layer of the notification service.

These cover every body-content branch from the spec table without
touching the DB or the network.
"""
from decimal import Decimal

from backend.services.notifications.payload import (
    NotificationLeg, NotificationContext, render_payload,
)


def _leg(side: str = "buy", pair: str = "ETH/AUD",
         notional: str = "100", mid: str | None = "3450",
         alloc_before: str = "18", alloc_after: str = "23") -> NotificationLeg:
    return NotificationLeg(
        side=side, pair=pair,
        notional_aud=Decimal(notional),
        mid=(Decimal(mid) if mid is not None else None),
        allocation_after_pct=Decimal(alloc_after),
        allocation_before_pct=Decimal(alloc_before),
    )


def _ctx(strategy_name: str = "Trend-Follower",
         execution_mode: str = "llm_agent",
         confidence: str | None = "medium",
         strategy_id: str = "00000000-0000-0000-0000-000000000abc",
         frontend_url: str = "https://app.example.com") -> NotificationContext:
    return NotificationContext(
        strategy_name=strategy_name,
        execution_mode=execution_mode,
        strategy_id=strategy_id,
        confidence=confidence,
        frontend_url=frontend_url,
    )


def test_single_leg_buy_with_full_context():
    out = render_payload([_leg()], _ctx())
    assert out["title"] == "BUY ETH/AUD — Trend-Follower"
    assert "100 AUD @ ~$3450 (mid)" in out["message"]
    assert "ETH allocation after: 23% (was 18%)" in out["message"]
    assert "Confidence: medium" in out["message"]
    assert out["click"] == "https://app.example.com/strategies/00000000-0000-0000-0000-000000000abc"
    assert "buy" in out["tags"] and "eth_aud" in out["tags"]


def test_single_leg_sell_renders_sell_title():
    out = render_payload([_leg(side="sell")], _ctx())
    assert out["title"].startswith("SELL ETH/AUD")
    assert "sell" in out["tags"]


def test_single_leg_missing_mid_omits_price_line():
    out = render_payload([_leg(mid=None)], _ctx())
    assert "@" not in out["message"]
    assert "100 AUD" in out["message"]


def test_single_leg_missing_confidence_renders_em_dash():
    out = render_payload([_leg()], _ctx(confidence=None))
    assert "Confidence: —" in out["message"]


def test_deterministic_strategy_omits_confidence_line():
    ctx = _ctx(execution_mode="deterministic", confidence=None,
               strategy_name="DCA-Baseline")
    out = render_payload([_leg()], ctx)
    assert "Confidence" not in out["message"]


def test_multi_leg_uses_rebalance_title_and_lists_legs():
    # DCA rebalance: four BUY legs. AUD is the cash side, not a tradable pair.
    legs = [_leg(pair="ETH/AUD", notional="500"),
            _leg(pair="SOL/AUD", notional="250", mid="140"),
            _leg(pair="LINK/AUD", notional="150", mid="22"),
            _leg(pair="ADA/AUD", notional="100", mid="0.45")]
    ctx = _ctx(strategy_name="DCA-Baseline", execution_mode="deterministic",
               confidence=None)
    out = render_payload(legs, ctx)
    assert out["title"] == "DCA-Baseline — 4 orders"
    assert out["message"].count("BUY") == 4
    # Compact form: base asset only, not the full pair.
    assert "BUY ETH" in out["message"]
    assert "BUY ADA" in out["message"]
    assert "Source: DCA-Baseline (deterministic)" in out["message"]
    assert "rebalance" in out["tags"]


def test_multi_leg_over_cap_truncates_to_four_and_appends_more():
    legs = [_leg(pair=f"PAIR{i}/AUD") for i in range(7)]
    out = render_payload(legs, _ctx(strategy_name="Many", execution_mode="deterministic"))
    assert out["title"] == "Many — 7 orders"
    assert "… +3 more" in out["message"]
    visible_buy_lines = [
        ln for ln in out["message"].splitlines() if ln.startswith("BUY")
    ]
    assert len(visible_buy_lines) == 4


def test_empty_legs_returns_none():
    assert render_payload([], _ctx()) is None


def test_click_omitted_when_frontend_url_blank():
    out = render_payload([_leg()], _ctx(frontend_url=""))
    assert out["click"] == ""
