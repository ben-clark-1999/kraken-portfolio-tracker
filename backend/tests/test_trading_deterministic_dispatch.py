from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

import backend.services.trading.strategy_loop as sl
from backend.models.trading import DeterministicConfig, RiskCaps, StrategyRow, CronTriggerEvent


class _FakeBook:
    def __init__(self, mid):
        self._mid = Decimal(str(mid))
        self.bids = [1]
        self.asks = [1]

    def mid(self):
        return self._mid


class _FakeExecutor:
    def __init__(self, mids):
        self._books = {p: _FakeBook(m) for p, m in mids.items()}
        self.submitted = []

    async def submit_order(self, **kw):
        self.submitted.append(kw)


def _strategy(cfg: DeterministicConfig):
    return StrategyRow(
        id=uuid4(), name="rule", execution_mode="deterministic",
        persona_key=None, deterministic_config=cfg,
        starting_balance_aud=Decimal("1000"),
        trigger_config={"triggers": [{"type": "cron", "expr": "0 9 * * *"}]},
        risk_caps=RiskCaps(max_order_aud=Decimal("250"),
                           max_single_asset_pct=Decimal("100"),
                           max_total_crypto_exposure_pct=Decimal("100")),
        status="active", dry_run=False,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def _patch_common(monkeypatch):
    # All-cash starting portfolio.
    monkeypatch.setattr(
        "backend.repositories.paper_positions_repo.get_all",
        lambda sid, schema="public": {"AUD": {"qty": "1000"}},
    )
    monkeypatch.setattr(sl, "_current_schema", "public", raising=False)
    monkeypatch.setattr(
        "backend.services.trading.decision_writer.write_agent_decision",
        lambda **kw: "decision-1",
    )


@pytest.mark.asyncio
async def test_dca_mode_submits_slice_split_by_weight(monkeypatch, _patch_common):
    cfg = DeterministicConfig(
        cadence_cron="0 9 * * 1", mode="dca", num_buys=12,
        allocations={"ETH/AUD": Decimal("0.5"), "SOL/AUD": Decimal("0.5")},
    )
    ex = _FakeExecutor({"ETH/AUD": Decimal("3000"), "SOL/AUD": Decimal("100")})
    sl.set_executor(ex, schema="public")
    await sl.invoke_deterministic_strategy(
        _strategy(cfg), CronTriggerEvent(expr="0 9 * * 1", ts=datetime.now(timezone.utc)))
    pairs = [o["pair"] for o in ex.submitted]
    assert "ETH/AUD" in pairs and "SOL/AUD" in pairs
    # Each submitted order's notional (qty*mid) is below the cap.
    for o in ex.submitted:
        mid = ex._books[o["pair"]].mid()
        assert o["qty"] * mid <= Decimal("250")


@pytest.mark.asyncio
async def test_trend_rule_enters_on_breakout(monkeypatch, _patch_common):
    cfg = DeterministicConfig(
        cadence_cron="0 9 * * *", mode="trend_rule",
        universe=["ETH/AUD"], min_move_pct=Decimal("1.5"),
    )
    # Mid 3060 is >1.5% above a flat 3000 trailing high → "long".
    ex = _FakeExecutor({"ETH/AUD": Decimal("3060")})
    sl.set_executor(ex, schema="public")
    monkeypatch.setattr(
        "backend.services.kraken_service.get_ohlc_hourly",
        lambda pair, bars=48: [{"close": "3000"} for _ in range(48)],
    )
    await sl.invoke_deterministic_strategy(
        _strategy(cfg), CronTriggerEvent(expr="0 9 * * *", ts=datetime.now(timezone.utc)))
    assert any(o["side"] == "buy" and o["pair"] == "ETH/AUD" for o in ex.submitted)


@pytest.mark.asyncio
async def test_trend_rule_no_flip_no_orders(monkeypatch, _patch_common):
    cfg = DeterministicConfig(
        cadence_cron="0 9 * * *", mode="trend_rule",
        universe=["ETH/AUD"], min_move_pct=Decimal("1.5"),
    )
    # Mid inside the band → "hold"; held set empty → no flip → no orders.
    ex = _FakeExecutor({"ETH/AUD": Decimal("3000")})
    sl.set_executor(ex, schema="public")
    monkeypatch.setattr(
        "backend.services.kraken_service.get_ohlc_hourly",
        lambda pair, bars=48: [{"close": "3000"} for _ in range(48)],
    )
    await sl.invoke_deterministic_strategy(
        _strategy(cfg), CronTriggerEvent(expr="0 9 * * *", ts=datetime.now(timezone.utc)))
    assert ex.submitted == []
