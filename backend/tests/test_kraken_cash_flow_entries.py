"""Tests for kraken_service.get_cash_flow_entries.

Pure unit tests with MagicMock + monkeypatch, matching the existing
test_kraken_service.py pattern. No live Kraken hits.
"""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from backend.services import kraken_service


def _make_user_with_ledger(pages: list[dict]) -> MagicMock:
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
    kraken_service._user = None
    kraken_service._market = None
    yield
    kraken_service._user = None
    kraken_service._market = None


def test_detects_deposit_entry(monkeypatch):
    ledger = {
        "LDEP1": {
            "asset": "ZAUD",
            "amount": "500.00",
            "refid": "DEPOSIT-REF-1",
            "time": 1779100000.0,
            "type": "deposit",
            "subtype": "",
        },
    }
    user = _make_user_with_ledger([{"count": 1, "ledger": ledger}])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    entries = kraken_service.get_cash_flow_entries(since=None)

    assert len(entries) == 1
    assert entries[0]["kraken_refid"] == "DEPOSIT-REF-1"
    assert entries[0]["kind"] == "deposit"
    assert entries[0]["amount_aud"] == Decimal("500.00")
    assert entries[0]["asset"] == "AUD"


def test_detects_withdrawal_entry(monkeypatch):
    ledger = {
        "LWD1": {
            "asset": "ZAUD",
            "amount": "-200.00",
            "refid": "WITHDRAW-REF-1",
            "time": 1779100000.0,
            "type": "withdrawal",
            "subtype": "",
        },
    }
    user = _make_user_with_ledger([{"count": 1, "ledger": ledger}])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    entries = kraken_service.get_cash_flow_entries(since=None)

    assert len(entries) == 1
    assert entries[0]["kind"] == "withdrawal"
    assert entries[0]["amount_aud"] == Decimal("200.00")  # absolute


def test_ignores_non_cash_flow_entries(monkeypatch):
    ledger = {
        "LRECV1": {
            "asset": "XETH", "amount": "0.05", "refid": "TRADE1",
            "time": 1779100000.0, "type": "receive", "subtype": "",
        },
        "LSPEND1": {
            "asset": "ZAUD", "amount": "-150.00", "refid": "TRADE1",
            "time": 1779100000.0, "type": "spend", "subtype": "",
        },
        "LSTAKE1": {
            "asset": "SOL.S", "amount": "0.001", "refid": "STAKE1",
            "time": 1779100000.0, "type": "staking", "subtype": "",
        },
    }
    user = _make_user_with_ledger([{"count": 3, "ledger": ledger}])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    entries = kraken_service.get_cash_flow_entries(since=None)

    assert entries == []


def test_marks_non_aud_deposit_with_asset_field(monkeypatch):
    """USDT/USDC deposits are returned with asset != 'AUD' so the
    caller can system_alert + skip them."""
    ledger = {
        "LUSDT1": {
            "asset": "USDT", "amount": "100.00", "refid": "USDT-REF",
            "time": 1779100000.0, "type": "deposit", "subtype": "",
        },
    }
    user = _make_user_with_ledger([{"count": 1, "ledger": ledger}])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    entries = kraken_service.get_cash_flow_entries(since=None)
    assert len(entries) == 1
    assert entries[0]["asset"] == "USDT"


def test_filters_by_since_timestamp(monkeypatch):
    ledger = {
        "LOLD": {
            "asset": "ZAUD", "amount": "100.00", "refid": "OLD-REF",
            "time": 1779000000.0, "type": "deposit", "subtype": "",
        },
        "LNEW": {
            "asset": "ZAUD", "amount": "200.00", "refid": "NEW-REF",
            "time": 1779200000.0, "type": "deposit", "subtype": "",
        },
    }
    user = _make_user_with_ledger([{"count": 2, "ledger": ledger}])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    since = datetime.fromtimestamp(1779100000.0, tz=timezone.utc)
    entries = kraken_service.get_cash_flow_entries(since=since)

    assert len(entries) == 1
    assert entries[0]["kraken_refid"] == "NEW-REF"


def test_pagination_aggregates_all_pages(monkeypatch):
    page1 = {
        "count": 2,
        "ledger": {
            "L1": {"asset": "ZAUD", "amount": "100", "refid": "R1",
                   "time": 1779000000.0, "type": "deposit", "subtype": ""},
        },
    }
    page2 = {
        "count": 2,
        "ledger": {
            "L2": {"asset": "ZAUD", "amount": "200", "refid": "R2",
                   "time": 1779100000.0, "type": "withdrawal", "subtype": ""},
        },
    }
    user = _make_user_with_ledger([page1, page2])
    monkeypatch.setattr(kraken_service, "_get_user", lambda: user)

    entries = kraken_service.get_cash_flow_entries(since=None)

    assert {e["kraken_refid"] for e in entries} == {"R1", "R2"}
