from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from backend.services import kraken_service


def _make_user_with_ledger(pages: list[dict]) -> MagicMock:
    """
    pages is a list of ledger-dict pages. Each page is {'count': total, 'ledger': {lid: entry}}.
    The mock returns pages in order of calls to get_ledgers_info(ofs=...).
    """
    user = MagicMock()
    call_count = {"n": 0}

    def fake_get_ledgers_info(ofs=0, **kwargs):
        idx = call_count["n"]
        call_count["n"] += 1
        if idx >= len(pages):
            return {"count": pages[0]["count"], "ledger": {}}
        return pages[idx]

    user.get_ledgers_info = fake_get_ledgers_info
    return user


@pytest.fixture(autouse=True)
def reset_kraken_singletons():
    """Ensure the module-level _user singleton doesn't leak between tests."""
    kraken_service._user = None
    kraken_service._market = None
    yield
    kraken_service._user = None
    kraken_service._market = None


def test_spend_and_receive_pair_becomes_one_buy_trade(monkeypatch):
    ledger = {
        "LRECV1": {
            "asset": "XETH",
            "amount": "0.0600262500",
            "fee": "0.0000000000",
            "refid": "TRADE1",
            "time": 1776200533.13158,
            "type": "receive",
            "subtype": "",
        },
        "LSPEND1": {
            "asset": "ZAUD",
            "amount": "-200.0000",
            "fee": "0.0000",
            "refid": "TRADE1",
            "time": 1776200533.13158,
            "type": "spend",
            "subtype": "",
        },
    }
    user = _make_user_with_ledger([{"count": 2, "ledger": ledger}])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    trades = kraken_service.get_trade_history()

    assert len(trades) == 1
    t = trades[0]
    assert t["trade_id"] == "TRADE1"
    assert t["asset"] == "ETH"
    assert t["time"] == 1776200533.13158
    assert Decimal(t["cost"]) == Decimal("200.0000")
    assert Decimal(t["vol"]) == Decimal("0.0600262500")
    # price = cost / vol
    expected_price = Decimal("200.0000") / Decimal("0.0600262500")
    assert Decimal(t["price"]) == expected_price


def test_transfer_entries_are_ignored(monkeypatch):
    ledger = {
        "LX1": {
            "asset": "SOL03.S",
            "amount": "2.4979904394",
            "fee": "0",
            "refid": "TRANSFER1",
            "time": 1776200610.0,
            "type": "transfer",
            "subtype": "spottostaking",
        },
        "LX2": {
            "asset": "SOL",
            "amount": "-2.4979904394",
            "fee": "0",
            "refid": "TRANSFER1",
            "time": 1776200610.0,
            "type": "transfer",
            "subtype": "spottostaking",
        },
    }
    user = _make_user_with_ledger([{"count": 2, "ledger": ledger}])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    assert kraken_service.get_trade_history() == []


def test_staking_rewards_are_ignored(monkeypatch):
    ledger = {
        "LSTAKE": {
            "asset": "SOL",
            "amount": "0.0123",
            "fee": "0",
            "refid": "STAKE1",
            "time": 1775817819.0,
            "type": "staking",
            "subtype": "",
        },
    }
    user = _make_user_with_ledger([{"count": 1, "ledger": ledger}])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    assert kraken_service.get_trade_history() == []


def test_deposit_and_withdrawal_are_ignored(monkeypatch):
    ledger = {
        "LDEP": {
            "asset": "ZAUD",
            "amount": "1000",
            "fee": "0",
            "refid": "DEP1",
            "time": 1776073285.0,
            "type": "deposit",
            "subtype": "",
        },
        "LWD": {
            "asset": "ZAUD",
            "amount": "-1990",
            "fee": "0",
            "refid": "WD1",
            "time": 1771331056.0,
            "type": "withdrawal",
            "subtype": "",
        },
    }
    user = _make_user_with_ledger([{"count": 2, "ledger": ledger}])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    assert kraken_service.get_trade_history() == []


def test_untracked_assets_are_skipped(monkeypatch):
    ledger = {
        "LR": {
            "asset": "EIGEN",
            "amount": "0.1",
            "fee": "0",
            "refid": "EIGEN_TRADE",
            "time": 1000.0,
            "type": "receive",
            "subtype": "",
        },
        "LS": {
            "asset": "ZAUD",
            "amount": "-50",
            "fee": "0",
            "refid": "EIGEN_TRADE",
            "time": 1000.0,
            "type": "spend",
            "subtype": "",
        },
    }
    user = _make_user_with_ledger([{"count": 2, "ledger": ledger}])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    assert kraken_service.get_trade_history() == []


def test_trades_sorted_newest_first(monkeypatch):
    ledger = {
        "LA_R": {"asset": "SOL", "amount": "1.0", "fee": "0", "refid": "A", "time": 1000.0, "type": "receive", "subtype": ""},
        "LA_S": {"asset": "ZAUD", "amount": "-100", "fee": "0", "refid": "A", "time": 1000.0, "type": "spend", "subtype": ""},
        "LB_R": {"asset": "SOL", "amount": "2.0", "fee": "0", "refid": "B", "time": 3000.0, "type": "receive", "subtype": ""},
        "LB_S": {"asset": "ZAUD", "amount": "-200", "fee": "0", "refid": "B", "time": 3000.0, "type": "spend", "subtype": ""},
        "LC_R": {"asset": "SOL", "amount": "3.0", "fee": "0", "refid": "C", "time": 2000.0, "type": "receive", "subtype": ""},
        "LC_S": {"asset": "ZAUD", "amount": "-300", "fee": "0", "refid": "C", "time": 2000.0, "type": "spend", "subtype": ""},
    }
    user = _make_user_with_ledger([{"count": 6, "ledger": ledger}])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    trades = kraken_service.get_trade_history()
    assert [t["trade_id"] for t in trades] == ["B", "C", "A"]


def test_incremental_sync_stops_at_known_trade_id(monkeypatch):
    ledger = {
        "LA_R": {"asset": "SOL", "amount": "1.0", "fee": "0", "refid": "A", "time": 1000.0, "type": "receive", "subtype": ""},
        "LA_S": {"asset": "ZAUD", "amount": "-100", "fee": "0", "refid": "A", "time": 1000.0, "type": "spend", "subtype": ""},
        "LB_R": {"asset": "SOL", "amount": "2.0", "fee": "0", "refid": "B", "time": 3000.0, "type": "receive", "subtype": ""},
        "LB_S": {"asset": "ZAUD", "amount": "-200", "fee": "0", "refid": "B", "time": 3000.0, "type": "spend", "subtype": ""},
        "LC_R": {"asset": "SOL", "amount": "3.0", "fee": "0", "refid": "C", "time": 2000.0, "type": "receive", "subtype": ""},
        "LC_S": {"asset": "ZAUD", "amount": "-300", "fee": "0", "refid": "C", "time": 2000.0, "type": "spend", "subtype": ""},
    }
    user = _make_user_with_ledger([{"count": 6, "ledger": ledger}])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    # Newest is B, then C, then A. If we already have C, we should only get B.
    trades = kraken_service.get_trade_history(since_trade_id="C")
    assert [t["trade_id"] for t in trades] == ["B"]


def test_pagination_combines_multiple_pages(monkeypatch):
    page1 = {
        "LA_R": {"asset": "SOL", "amount": "1.0", "fee": "0", "refid": "A", "time": 1000.0, "type": "receive", "subtype": ""},
        "LA_S": {"asset": "ZAUD", "amount": "-100", "fee": "0", "refid": "A", "time": 1000.0, "type": "spend", "subtype": ""},
    }
    page2 = {
        "LB_R": {"asset": "SOL", "amount": "2.0", "fee": "0", "refid": "B", "time": 3000.0, "type": "receive", "subtype": ""},
        "LB_S": {"asset": "ZAUD", "amount": "-200", "fee": "0", "refid": "B", "time": 3000.0, "type": "spend", "subtype": ""},
    }
    user = _make_user_with_ledger([
        {"count": 4, "ledger": page1},
        {"count": 4, "ledger": page2},
    ])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    trades = kraken_service.get_trade_history()
    assert sorted(t["trade_id"] for t in trades) == ["A", "B"]


def test_api_exception_becomes_kraken_service_error(monkeypatch):
    user = MagicMock()
    user.get_ledgers_info.side_effect = RuntimeError("boom")
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    with pytest.raises(kraken_service.KrakenServiceError) as exc_info:
        kraken_service.get_trade_history()
    assert "get_trade_history failed" in str(exc_info.value)
